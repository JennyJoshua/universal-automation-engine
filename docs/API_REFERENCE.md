# REST API Reference

## Overview

The REST API exposes plugin discovery and controlled capability execution through FastAPI. It does not require a separate frontend.

The application is created with `create_app(plugin_registry, executor, api_key_authenticator=...)`. The host supplies the registry, executor, and a trusted authenticator. A legacy static API-key mapping remains supported for compatibility.

## Authentication

All endpoints except `GET /health` require an API key in the `X-API-Key` header.

API keys:

- Must be at least 32 characters.
- Are hashed with SHA-256 before being retained by the authenticator.
- Are compared using constant-time digest comparison.
- Map to trusted server-side `ExecutionPrincipal` objects.
- Must be supplied by the host from a secure configuration or secret store.

The managed API-key lifecycle is available through APIKeyManager:

- Keys use a high-entropy random secret and a non-secret key identifier.
- Only a SHA-256 digest of the secret is stored.
- Issuance requires a host-trusted subject, permissions, and timezone-aware expiry.
- Authentication rejects unknown, tampered, expired, and revoked keys.
- Rotation issues a replacement and revokes the previous key.
- Revocation invalidates a key immediately.
- The raw key is returned only by issue/rotate and must be delivered securely once.

The default InMemoryAPIKeyStore is suitable for development and small single-process deployments. Hosts can implement the APIKeyStore protocol for persistent storage. The legacy static mapping remains for compatibility but does not provide lifecycle operations. Never commit API keys to source control or expose them in logs.

Example request header:

```http
X-API-Key: <your-secret-api-key>
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Public health check |
| GET | `/v1/plugins` | List registered plugins |
| GET | `/v1/plugins/{plugin_id}` | Retrieve one plugin manifest |
| GET | `/v1/capabilities` | List all declared capabilities |
| GET | `/v1/plugins/{plugin_id}/capabilities/{capability_name}` | Retrieve one capability |
| POST | `/v1/executions` | Execute an authorized capability |

FastAPI's generated interactive API documentation is available at `/docs` when the host application runs the service.

## Execute a capability

Example request:

```http
POST /v1/executions
Content-Type: application/json
X-API-Key: <your-secret-api-key>
```

```json
{
  "request_id": "request-456",
  "plugin_id": "example.text-tools",
  "capability_name": "normalize_text",
  "input_data": {
    "text": " Hello "
  }
}
```

The response includes the request ID, plugin version, capability name, validated output, handler duration, and completion timestamp.

The API never accepts client-supplied permission claims or approval grants. The authenticated principal is resolved from the server-side API-key mapping. Approval-required capabilities remain blocked unless a future trusted approval integration supplies a valid grant.

## HTTP status codes

| Status | Meaning |
|---|---|
| 200 | Request completed successfully |
| 401 | Missing or invalid API key |
| 403 | Permission or approval policy denied execution |
| 404 | Plugin or capability not found |
| 409 | Capability handler is not registered |
| 422 | Invalid request body or capability input |
| 500 | Handler failure or invalid handler output |

Error responses avoid exposing internal handler exception details.

## Host setup example

```python
from fastapi import FastAPI

from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.interfaces.api import create_app
from datetime import UTC, datetime, timedelta

from universal_automation.security import APIKeyManager, AuthorizationPolicy
from universal_automation.interfaces.api.auth import ManagedAPIKeyAuthenticator

registry = PluginRegistry()
# Register plugin manifests and trusted handlers during host startup.

executor = CapabilityExecutor(registry, AuthorizationPolicy())
key_manager = APIKeyManager()

issued = key_manager.issue(
    subject_id="integration-client",
    permissions={"files.read"},
    expires_at=datetime.now(UTC) + timedelta(days=30),
)

app: FastAPI = create_app(
    registry,
    executor,
    api_key_authenticator=ManagedAPIKeyAuthenticator(key_manager),
)

# Deliver issued.api_key securely to the client once. Do not log or commit it.
# Rotation: key_manager.rotate(issued.key_id, new_expiry)
# Revocation: key_manager.revoke(issued.key_id)
```

Replace the example key with a randomly generated secret supplied through secure host configuration. Do not use the example value in a real deployment.

## Current limitations

- The default managed key store is in-memory; hosts must provide a persistent APIKeyStore for multi-process or durable deployments.
- No OAuth, JWT, user registration, or public API-key management endpoints.
- The host is responsible for secure delivery of newly issued keys and for configuring a persistent store where required.
- No approval workflow; approval-required capabilities are denied by default.
- No production deployment configuration is included.
