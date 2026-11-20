"""Protocol-level tests for the MCP adapter."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mcp import Client
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.interfaces.mcp import (
    MCPAdapter,
    MCPAdapterError,
    principal_from_access_token,
)
from universal_automation.security import (
    ApprovalGrant,
    AuthorizationPolicy,
    ExecutionPrincipal,
)


class StaticTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        if token == "valid-token":
            return AccessToken(
                token=token,
                client_id="mcp-client",
                subject="mcp-user",
                scopes=["text.process"],
                resource="http://127.0.0.1:8000/mcp",
            )
        return None


def make_adapter(
    *,
    permissions: set[str] | None = None,
    approval_required: bool = False,
    handler=None,
    approval_provider=None,
) -> MCPAdapter:
    manifest = PluginManifest(
        plugin_id="example.text-tools",
        display_name="Example Text Tools",
        version="1.0.0",
        description="Text processing capabilities for MCP tests.",
        capabilities=(
            CapabilitySpec(
                name="normalize_text",
                description="Normalize a supplied text value.",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string", "minLength": 1}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"normalized": {"type": "string"}},
                    "required": ["normalized"],
                    "additionalProperties": False,
                },
                permissions=("text.process",),
                destructive=approval_required,
                approval_required=approval_required,
            ),
        ),
    )
    registry = PluginRegistry()
    registry.register(manifest)
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    if handler is not None:
        executor.register_handler("example.text-tools", "normalize_text", handler)

    principal = ExecutionPrincipal(
        subject_id="local-user",
        permissions=permissions if permissions is not None else {"text.process"},
    )
    return MCPAdapter(
        registry,
        executor,
        local_principal=principal,
        approval_provider=approval_provider,
    )


def test_mcp_lists_registered_capabilities_and_schemas() -> None:
    adapter = make_adapter()

    async def scenario() -> None:
        async with Client(adapter._server) as client:
            result = await client.list_tools()

        assert len(result.tools) == 1
        tool = result.tools[0]
        assert tool.name.startswith("uae_")
        assert "example.text-tools@1.0.0" in (tool.description or "")
        assert tool.input_schema["required"] == ["text"]
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.destructive_hint is False

    asyncio.run(scenario())


def test_mcp_tool_call_uses_shared_capability_executor() -> None:
    adapter = make_adapter(
        handler=lambda data: {"normalized": data["text"].strip().lower()},
    )

    async def scenario() -> None:
        async with Client(adapter._server) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                tools.tools[0].name,
                {"text": " Hello MCP "},
            )

        assert result.is_error is False
        assert result.structured_content == {"normalized": "hello mcp"}

    asyncio.run(scenario())


def test_mcp_enforces_permissions_before_handler_invocation() -> None:
    called = False

    def handler(data: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"normalized": "not allowed"}

    adapter = make_adapter(permissions=set(), handler=handler)

    async def scenario() -> None:
        async with Client(adapter._server) as client:
            tools = await client.list_tools()
            result = await client.call_tool(tools.tools[0].name, {"text": "hello"})

        assert result.is_error is True
        assert result.content[0].text == "Execution is not authorized"
        assert called is False

    asyncio.run(scenario())


def test_mcp_approval_required_tool_is_denied_without_trusted_approval() -> None:
    adapter = make_adapter(
        approval_required=True,
        handler=lambda data: {"normalized": "should not run"},
    )

    async def scenario() -> None:
        async with Client(adapter._server) as client:
            tools = await client.list_tools()
            result = await client.call_tool(tools.tools[0].name, {"text": "hello"})

        assert result.is_error is True
        assert result.content[0].text == "Execution is not authorized"

    asyncio.run(scenario())


def test_mcp_trusted_approval_provider_can_authorize_approved_tool() -> None:
    def approval_provider(token, request_id, registered):
        now = datetime.now(UTC)
        return ApprovalGrant(
            approval_id="approval-mcp",
            subject_id="local-user",
            plugin_id=registered.plugin_id,
            capability_name=registered.capability.name,
            request_id=request_id,
            approved_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(minutes=1),
        )

    adapter = make_adapter(
        approval_required=True,
        handler=lambda data: {"normalized": data["text"].strip()},
        approval_provider=approval_provider,
    )

    async def scenario() -> None:
        async with Client(adapter._server) as client:
            tools = await client.list_tools()
            result = await client.call_tool(tools.tools[0].name, {"text": " approved "})

        assert result.is_error is False
        assert result.structured_content == {"normalized": "approved"}

    asyncio.run(scenario())


def test_mcp_handler_errors_do_not_expose_internal_details() -> None:
    def failing_handler(data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("private diagnostic")

    adapter = make_adapter(handler=failing_handler)

    async def scenario() -> None:
        async with Client(adapter._server) as client:
            tools = await client.list_tools()
            result = await client.call_tool(tools.tools[0].name, {"text": "hello"})

        assert result.is_error is True
        assert result.content[0].text == "Capability execution failed"
        assert "private diagnostic" not in result.content[0].text

    asyncio.run(scenario())


def test_mcp_requires_a_trusted_identity_configuration() -> None:
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())

    with pytest.raises(ValueError, match="trusted local principal"):
        MCPAdapter(registry, executor)


def test_stdio_requires_an_explicit_local_principal() -> None:
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    adapter = MCPAdapter(
        registry,
        executor,
        token_verifier=StaticTokenVerifier(),
        auth_settings=AuthSettings(
            issuer_url=AnyHttpUrl("https://auth.example.com"),
            resource_server_url=AnyHttpUrl("http://127.0.0.1:8000/mcp"),
            required_scopes=[],
            validate_token_resource=True,
        ),
    )

    with pytest.raises(MCPAdapterError, match="local principal"):
        asyncio.run(adapter.run_stdio_async())


def test_streamable_http_requires_oauth_configuration() -> None:
    adapter = make_adapter()

    with pytest.raises(MCPAdapterError, match="OAuth TokenVerifier"):
        adapter.streamable_http_app()


def test_streamable_http_rejects_nonlocal_host_without_security_allowlist() -> None:
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    adapter = MCPAdapter(
        registry,
        executor,
        token_verifier=StaticTokenVerifier(),
        auth_settings=AuthSettings(
            issuer_url=AnyHttpUrl("https://auth.example.com"),
            resource_server_url=AnyHttpUrl("https://automation.example.com/mcp"),
            required_scopes=[],
            validate_token_resource=True,
        ),
    )

    with pytest.raises(MCPAdapterError, match="transport_security"):
        adapter.streamable_http_app(host="0.0.0.0")


def test_verified_access_token_maps_to_trusted_principal() -> None:
    token = AccessToken(
        token="verified-token",
        client_id="mcp-client",
        subject="mcp-user",
        scopes=["files.read", "text.process"],
        resource="https://automation.example.com/mcp",
    )

    principal = principal_from_access_token(token)

    assert principal.subject_id == "mcp-user"
    assert principal.permissions == frozenset({"files.read", "text.process"})


def test_oauth_protected_streamable_http_app_can_be_created() -> None:
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    adapter = MCPAdapter(
        registry,
        executor,
        token_verifier=StaticTokenVerifier(),
        auth_settings=AuthSettings(
            issuer_url=AnyHttpUrl("https://auth.example.com"),
            resource_server_url=AnyHttpUrl("http://127.0.0.1:8000/mcp"),
            required_scopes=[],
            validate_token_resource=True,
        ),
    )

    app = adapter.streamable_http_app(host="127.0.0.1")

    assert app is not None
