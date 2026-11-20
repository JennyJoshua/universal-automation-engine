# MCP Integration

## Overview

Universal Automation Engine exposes registered plugin capabilities as dynamic Model Context Protocol (MCP) tools using the official MCP Python SDK v2.

Install the optional MCP extra:

```bash
python -m pip install -e ".[mcp]"
```

The MCP adapter and REST API use the same `PluginRegistry`, `CapabilityExecutor`, and `AuthorizationPolicy`. MCP is an interface, not a second automation implementation.

## Dynamic tool discovery

Each registered capability becomes one MCP tool. Tool names use a stable hash of the plugin identifier plus the capability name, while the tool description includes the human-readable plugin ID and version.

The MCP tool publishes the capability's input and output JSON Schemas and safety annotations. Tool annotations are hints to clients; the executor's server-side permission and approval checks remain authoritative.

## Local stdio

Local stdio requires an explicitly configured trusted principal:

```python
from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.interfaces.mcp import MCPAdapter
from universal_automation.security import AuthorizationPolicy, ExecutionPrincipal

registry = PluginRegistry()
# Register validated manifests and trusted handlers first.

executor = CapabilityExecutor(registry, AuthorizationPolicy())
local_principal = ExecutionPrincipal(
    subject_id="local-user",
    permissions={"files.read"},
)

adapter = MCPAdapter(
    registry,
    executor,
    local_principal=local_principal,
)

adapter.run_stdio()
```

The local principal is trusted host configuration. Do not derive it from untrusted command-line arguments or tool-call payloads.

For embedding in an existing async host, use `await adapter.run_stdio_async()`.

## Remote Streamable HTTP

Remote HTTP is disabled unless both a host-provided OAuth token verifier and matching `AuthSettings` are supplied. The adapter uses the SDK's verified access-token context; it does not trust raw HTTP headers or client-supplied permission claims.

```python
from mcp.server.auth.settings import AuthSettings

adapter = MCPAdapter(
    registry,
    executor,
    token_verifier=host_token_verifier,
    auth_settings=AuthSettings(
        issuer_url="https://identity.example.com",
        resource_server_url="https://automation.example.com/mcp",
        required_scopes=[],
        validate_token_resource=True,
    ),
)

app = adapter.streamable_http_app(
    host="127.0.0.1",
    streamable_http_path="/mcp",
)
```

The host supplies and operates the OAuth identity provider and token verifier. The default token-to-principal resolver maps the verified token subject (or client ID) to `subject_id` and token scopes to execution permissions. A custom `principal_resolver` can apply a host-specific mapping.

When binding to a non-local host, provide explicit `TransportSecuritySettings` allowlists for expected hosts and origins. Do not disable DNS-rebinding protection for public deployments.

## Approval integration

An optional trusted `approval_provider` can supply a request-bound `ApprovalGrant` for a capability. It receives the verified access token (or `None` for local stdio), request ID, and registered capability.

The provider must consult a trusted approval workflow. It must never treat a client-supplied boolean or MCP tool argument as approval. Without a provider, approval-required capabilities are denied by the execution policy.

## ChatGPT compatibility and account requirements

The server implements standard MCP tools and can be tested with compatible MCP clients independently of ChatGPT.

Connecting a custom MCP server to ChatGPT requires an eligible ChatGPT workspace and a reachable remote HTTPS endpoint. Current OpenAI guidance states:

- Full custom MCP support, including write/modify actions, is available for ChatGPT Business and Enterprise/Edu workspaces on web.
- Pro supports more limited custom MCP use for read/fetch actions.
- Free is not listed as a supported plan for custom MCP server connections.
- Custom MCP connections are not available directly in the ChatGPT mobile app.
- OAuth providers used with ChatGPT should support refresh tokens (commonly the `offline_access` scope) to maintain connectivity.

The current Free ChatGPT account cannot connect to this custom MCP server through the documented custom-MCP workflow. The server can still be developed and tested locally or with other MCP clients. We will not purchase or upgrade a plan as part of this implementation.

## Security boundaries and limitations

- The MCP SDK is an optional dependency; REST-only installations do not need it.
- Local stdio uses one explicitly configured local principal.
- Remote HTTP requires a host-supplied OAuth TokenVerifier and AuthSettings.
- OAuth authorization-server implementation and identity-provider selection are not included.
- API keys used by the REST API are not treated as OAuth tokens for MCP.
- The adapter does not create or persist approvals.
- Third-party plugin code is not dynamically loaded.
- The executor remains synchronous and in-process; no sandbox or hard timeout is provided.
- Tool annotations are advisory; authorization is enforced by the executor.

## Official references

- [MCP Python SDK v2 documentation](https://py.sdk.modelcontextprotocol.io/)
- [MCP Python SDK v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
- [OpenAI: Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [OpenAI: Building with the Apps SDK](https://help.openai.com/en/articles/12515353-building-with-the-apps-sdk)
