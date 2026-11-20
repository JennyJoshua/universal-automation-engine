"""MCP v2 adapter exposing registered capabilities as dynamic tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from mcp import types
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings

from universal_automation.core.execution import (
    CapabilityExecutor,
    ExecutionRequest,
    HandlerExecutionError,
    HandlerNotRegisteredError,
    InputValidationError,
    OutputValidationError,
)
from universal_automation.core.registry import (
    CapabilityNotFoundError,
    PluginNotFoundError,
    PluginRegistry,
    RegisteredCapability,
)
from universal_automation.security import (
    ApprovalGrant,
    AuthorizationError,
    ExecutionPrincipal,
)

PrincipalResolver = Callable[[AccessToken], ExecutionPrincipal]
ApprovalProvider = Callable[
    [AccessToken | None, str, RegisteredCapability],
    ApprovalGrant | None,
]


class MCPAdapterError(RuntimeError):
    """Base exception for MCP adapter configuration errors."""


class MCPAuthenticationError(MCPAdapterError):
    """Raised when an MCP call has no trusted execution identity."""


def principal_from_access_token(token: AccessToken) -> ExecutionPrincipal:
    """Map verified OAuth token subject and scopes into execution permissions."""
    identity = token.subject or token.client_id
    if not identity:
        raise MCPAuthenticationError("Verified access token has no subject or client ID")

    issuer = (token.claims or {}).get("iss")
    subject_id = f"{issuer}:{identity}" if issuer else identity
    if len(subject_id) > 200:
        subject_id = "oauth:" + hashlib.sha256(subject_id.encode("utf-8")).hexdigest()

    return ExecutionPrincipal(
        subject_id=subject_id,
        permissions=frozenset(token.scopes),
    )


class MCPAdapter:
    """Expose plugin capabilities through MCP stdio and authenticated HTTP.

    Local stdio uses an explicitly configured trusted principal. Streamable HTTP
    is available only with a host-provided OAuth token verifier and AuthSettings.
    """

    def __init__(
        self,
        plugin_registry: PluginRegistry,
        executor: CapabilityExecutor,
        *,
        local_principal: ExecutionPrincipal | None = None,
        token_verifier: TokenVerifier | None = None,
        auth_settings: AuthSettings | None = None,
        principal_resolver: PrincipalResolver | None = None,
        approval_provider: ApprovalProvider | None = None,
    ) -> None:
        if executor.plugin_registry is not plugin_registry:
            raise ValueError("MCP adapter and executor must use the same plugin registry instance")
        if (token_verifier is None) != (auth_settings is None):
            raise ValueError("token_verifier and auth_settings must be supplied together")
        if local_principal is None and token_verifier is None:
            raise ValueError("Configure a trusted local principal or OAuth token verifier")

        self._plugin_registry = plugin_registry
        self._executor = executor
        self._local_principal = (
            local_principal.model_copy(deep=True) if local_principal is not None else None
        )
        self._token_verifier = token_verifier
        self._auth_settings = auth_settings
        self._principal_resolver = principal_resolver or principal_from_access_token
        self._approval_provider = approval_provider

        self._server = Server(
            "Universal Automation Engine",
            version="0.1.0",
            description="Dynamic automation tools backed by Universal Automation Engine.",
            instructions=(
                "Discover available capabilities before execution. "
                "Tool permissions and approval requirements are enforced by the server."
            ),
            get_tool_input_schema=self._get_tool_input_schema,
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )

    def _tool_name(self, registered: RegisteredCapability) -> str:
        plugin_hash = hashlib.sha256(registered.plugin_id.encode("utf-8")).hexdigest()[:16]
        return f"uae_{plugin_hash}_{registered.capability.name}"

    def _tool_index(self) -> dict[str, RegisteredCapability]:
        index: dict[str, RegisteredCapability] = {}
        for registered in self._plugin_registry.list_capabilities():
            name = self._tool_name(registered)
            if name in index:
                raise MCPAdapterError("MCP tool-name collision detected")
            index[name] = registered
        return index

    def _get_tool_input_schema(self, tool_name: str) -> dict[str, Any] | None:
        registered = self._tool_index().get(tool_name)
        if registered is None:
            return None
        return registered.capability.input_schema

    async def _list_tools(
        self,
        _ctx: ServerRequestContext[Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        tools: list[types.Tool] = []
        for tool_name, registered in sorted(self._tool_index().items()):
            capability = registered.capability
            tools.append(
                types.Tool(
                    name=tool_name,
                    description=(
                        f"{registered.plugin_id}@{registered.plugin_version}: "
                        f"{capability.description}"
                    ),
                    input_schema=capability.input_schema,
                    output_schema=capability.output_schema,
                    annotations=types.ToolAnnotations(
                        title=capability.name,
                        read_only_hint=False,
                        destructive_hint=capability.destructive,
                        idempotent_hint=False,
                        open_world_hint=True,
                    ),
                )
            )
        return types.ListToolsResult(tools=tools)

    def _resolve_principal(self, token: AccessToken | None) -> ExecutionPrincipal:
        if token is None:
            if self._local_principal is None:
                raise MCPAuthenticationError("No trusted local or OAuth identity is available")
            return self._local_principal.model_copy(deep=True)

        principal = self._principal_resolver(token)
        if not isinstance(principal, ExecutionPrincipal):
            raise TypeError("principal_resolver must return an ExecutionPrincipal")
        return principal.model_copy(deep=True)

    async def _call_tool(
        self,
        ctx: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        registered = self._tool_index().get(params.name)
        if registered is None:
            return types.CallToolResult(
                content=[types.TextContent(text="Unknown automation tool")],
                is_error=True,
            )

        token = get_access_token()
        request_id = str(ctx.request_id) if ctx.request_id is not None else uuid4().hex

        try:
            principal = self._resolve_principal(token)
            request = ExecutionRequest(
                request_id=request_id,
                plugin_id=registered.plugin_id,
                capability_name=registered.capability.name,
                input_data=params.arguments or {},
            )
            approval = (
                self._approval_provider(token, request_id, registered)
                if self._approval_provider is not None
                else None
            )
            result = await asyncio.to_thread(
                self._executor.execute,
                request,
                principal,
                approval,
            )
        except AuthorizationError:
            return self._tool_error("Execution is not authorized")
        except InputValidationError:
            return self._tool_error("Input does not satisfy the declared capability schema")
        except (HandlerNotRegisteredError, PluginNotFoundError, CapabilityNotFoundError):
            return self._tool_error("Capability is unavailable")
        except (HandlerExecutionError, OutputValidationError):
            return self._tool_error("Capability execution failed")
        except Exception:
            return self._tool_error("Automation request could not be completed")

        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(result.output_data, sort_keys=True))],
            structured_content=result.output_data,
        )

    @staticmethod
    def _tool_error(message: str) -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(text=message)],
            is_error=True,
        )

    async def run_stdio_async(self) -> None:
        """Run the MCP server over stdio using the configured local principal."""
        if self._local_principal is None:
            raise MCPAdapterError("stdio transport requires an explicit local principal")

        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream,
                write_stream,
                self._server.create_initialization_options(),
            )

    def run_stdio(self) -> None:
        """Synchronous entry point for launching the local stdio server."""
        asyncio.run(self.run_stdio_async())

    def streamable_http_app(
        self,
        *,
        host: str = "127.0.0.1",
        streamable_http_path: str = "/mcp",
        transport_security: TransportSecuritySettings | None = None,
        stateless_http: bool = True,
        json_response: bool = True,
    ) -> Any:
        """Create an OAuth-protected Streamable HTTP ASGI app.

        Non-local hosts must supply explicit transport-security allowlists to
        protect against DNS rebinding and unintended Host/Origin values.
        """
        if self._token_verifier is None or self._auth_settings is None:
            raise MCPAdapterError(
                "Streamable HTTP requires a host-provided OAuth TokenVerifier and AuthSettings"
            )
        if host not in ("127.0.0.1", "localhost", "::1") and transport_security is None:
            raise MCPAdapterError(
                "Non-local Streamable HTTP hosts require explicit transport_security settings"
            )

        return self._server.streamable_http_app(
            streamable_http_path=streamable_http_path,
            json_response=json_response,
            stateless_http=stateless_http,
            transport_security=transport_security,
            host=host,
            auth=self._auth_settings,
            token_verifier=self._token_verifier,
        )
