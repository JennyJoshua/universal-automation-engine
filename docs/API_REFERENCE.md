# REST API Reference

## Overview

The REST API exposes plugin discovery and controlled capability execution through FastAPI. It does not require a separate frontend.

The application is created with `create_app(plugin_registry, executor, api_keys)`. The host application supplies the registry, executor, and API-key-to-principal mapping.

## Authentication

All endpoints except `GET /health` require an API key in the `X-API-Key` header.

API keys:

- Must be at least 32 characters.
- Are hashed with SHA-256 before being retained by the authenticator.
- Are compared using constant-time digest comparison.
- Map to trusted server-side `ExecutionPrincipal` objects.
- Must be supplied by the host from a secure configuration or secret store.

The authenticator does not provide API-key issuance, rotation, persistence, or a management interface. Never commit API keys to source control or expose them in logs.

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
from universal_automation.security import AuthorizationPolicy, ExecutionPrincipal

registry = PluginRegistry()
# Register plugin manifests and trusted handlers during host startup.

executor = CapabilityExecutor(registry, AuthorizationPolicy())

api_keys = {
    "replace-with-a-random-secret-of-at-least-32-characters": ExecutionPrincipal(
        subject_id="integration-client",
        permissions={"files.read"},
    )
}

app: FastAPI = create_app(registry, executor, api_keys)
```

Replace the example key with a randomly generated secret supplied through secure host configuration. Do not use the example value in a real deployment.

## Current limitations

- API keys and principals are supplied in memory by the host.
- No OAuth, JWT, user registration, or API-key management endpoints.
- No persistent key store or revocation service.
- No approval workflow; approval-required capabilities are denied by default.
- No production deployment configuration is included.
