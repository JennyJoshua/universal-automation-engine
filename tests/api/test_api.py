"""Tests for the authenticated REST API."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.interfaces.api.app import create_app
from universal_automation.interfaces.api.auth import (
    APIKeyAuthenticator,
    AuthenticationError,
    ManagedAPIKeyAuthenticator,
)
from universal_automation.security import APIKeyManager, AuthorizationPolicy, ExecutionPrincipal

VALID_API_KEY = "uae-test-key-" + ("x" * 32)


def make_client(
    *,
    permissions: set[str] | None = None,
    approval_required: bool = False,
    handler=None,
    api_key_manager: APIKeyManager | None = None,
) -> TestClient:
    manifest = PluginManifest(
        plugin_id="example.text-tools",
        display_name="Example Text Tools",
        version="1.0.0",
        description="Text processing capabilities for API tests.",
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
        subject_id="api-user",
        permissions=permissions if permissions is not None else {"text.process"},
    )
    if api_key_manager is not None:
        return TestClient(
            create_app(
                registry,
                executor,
                api_key_authenticator=ManagedAPIKeyAuthenticator(api_key_manager),
            )
        )
    return TestClient(create_app(registry, executor, {VALID_API_KEY: principal}))


def execution_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "request_id": "request-api-1",
        "plugin_id": "example.text-tools",
        "capability_name": "normalize_text",
        "input_data": {"text": " Hello "},
    }
    body.update(overrides)
    return body


def test_health_endpoint_is_public() -> None:
    client = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_endpoint_rejects_missing_api_key() -> None:
    client = make_client()

    response = client.get("/v1/plugins")

    assert response.status_code == 401


def test_protected_endpoint_rejects_invalid_api_key() -> None:
    client = make_client()

    response = client.get("/v1/plugins", headers={"X-API-Key": "invalid"})

    assert response.status_code == 401


def test_valid_api_key_can_list_plugins() -> None:
    client = make_client()

    response = client.get("/v1/plugins", headers={"X-API-Key": VALID_API_KEY})

    assert response.status_code == 200
    assert response.json()[0]["plugin_id"] == "example.text-tools"


def test_plugin_lookup_returns_404_for_unknown_plugin() -> None:
    client = make_client()

    response = client.get(
        "/v1/plugins/missing.plugin",
        headers={"X-API-Key": VALID_API_KEY},
    )

    assert response.status_code == 404


def test_capability_discovery_endpoints_work() -> None:
    client = make_client()
    headers = {"X-API-Key": VALID_API_KEY}

    listed = client.get("/v1/capabilities", headers=headers)
    detail = client.get(
        "/v1/plugins/example.text-tools/capabilities/normalize_text",
        headers=headers,
    )

    assert listed.status_code == 200
    assert listed.json()[0]["capability"]["name"] == "normalize_text"
    assert detail.status_code == 200
    assert detail.json()["plugin_version"] == "1.0.0"


def test_unknown_capability_returns_404() -> None:
    client = make_client()

    response = client.get(
        "/v1/plugins/example.text-tools/capabilities/missing_action",
        headers={"X-API-Key": VALID_API_KEY},
    )

    assert response.status_code == 404


def test_valid_execution_uses_authenticated_principal() -> None:
    client = make_client(handler=lambda data: {"normalized": data["text"].strip().lower()})

    response = client.post(
        "/v1/executions",
        headers={"X-API-Key": VALID_API_KEY},
        json=execution_body(),
    )

    assert response.status_code == 200
    assert response.json()["output_data"] == {"normalized": "hello"}


def test_invalid_execution_input_returns_422() -> None:
    client = make_client(handler=lambda data: {"normalized": "unused"})

    response = client.post(
        "/v1/executions",
        headers={"X-API-Key": VALID_API_KEY},
        json=execution_body(input_data={"text": 123}),
    )

    assert response.status_code == 422


def test_client_cannot_supply_approval_grant_or_permissions() -> None:
    client = make_client(handler=lambda data: {"normalized": "unused"})
    body = execution_body(
        approval={"approval_id": "client-forged"},
        permissions=["text.process", "admin"],
    )

    response = client.post(
        "/v1/executions",
        headers={"X-API-Key": VALID_API_KEY},
        json=body,
    )

    assert response.status_code == 422


def test_missing_permission_returns_403() -> None:
    client = make_client(
        permissions=set(),
        handler=lambda data: {"normalized": "unused"},
    )

    response = client.post(
        "/v1/executions",
        headers={"X-API-Key": VALID_API_KEY},
        json=execution_body(),
    )

    assert response.status_code == 403


def test_approval_required_execution_is_denied_without_trusted_approval() -> None:
    client = make_client(
        approval_required=True,
        handler=lambda data: {"normalized": "should not execute"},
    )

    response = client.post(
        "/v1/executions",
        headers={"X-API-Key": VALID_API_KEY},
        json=execution_body(),
    )

    assert response.status_code == 403


def test_handler_internal_error_is_not_exposed() -> None:
    def failing_handler(data: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("secret internal diagnostic")

    client = make_client(handler=failing_handler)

    response = client.post(
        "/v1/executions",
        headers={"X-API-Key": VALID_API_KEY},
        json=execution_body(),
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Capability execution failed"
    assert "secret internal diagnostic" not in response.text


def test_authenticator_rejects_short_api_keys() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        APIKeyAuthenticator({"short": ExecutionPrincipal(subject_id="user-1")})


def test_authenticator_returns_trusted_principal_for_valid_key() -> None:
    principal = ExecutionPrincipal(subject_id="api-user", permissions={"text.process"})
    authenticator = APIKeyAuthenticator({VALID_API_KEY: principal})

    authenticated = authenticator.authenticate(VALID_API_KEY)

    assert authenticated == principal


def test_authenticator_rejects_unknown_key() -> None:
    authenticator = APIKeyAuthenticator({VALID_API_KEY: ExecutionPrincipal(subject_id="api-user")})

    with pytest.raises(AuthenticationError):
        authenticator.authenticate("z" * 40)


def test_app_rejects_mismatched_registry_and_executor() -> None:
    registry = PluginRegistry()
    registry.register(
        PluginManifest(
            plugin_id="example.simple",
            display_name="Simple Plugin",
            version="1.0.0",
            description="Minimal registry consistency test.",
            capabilities=(
                CapabilitySpec(
                    name="ping",
                    description="Return a ping result.",
                    input_schema={"type": "object", "properties": {}},
                    output_schema={"type": "object", "properties": {}},
                ),
            ),
        )
    )
    executor = CapabilityExecutor(registry, AuthorizationPolicy())

    with pytest.raises(ValueError, match="same plugin registry"):
        create_app(
            PluginRegistry(),
            executor,
            {VALID_API_KEY: ExecutionPrincipal(subject_id="api-user")},
        )

def test_managed_api_key_authenticator_protects_rest_endpoints():
    manager = APIKeyManager()
    issued = manager.issue(
        "managed-api-user",
        {"text.process"},
        datetime.now(UTC) + timedelta(days=1),
    )
    client = make_client(
        handler=lambda data: {"normalized": data["text"].strip().lower()},
        api_key_manager=manager,
    )

    response = client.get(
        "/v1/plugins",
        headers={"X-API-Key": issued.api_key},
    )

    assert response.status_code == 200
    assert response.json()[0]["plugin_id"] == "example.text-tools"


def test_app_rejects_ambiguous_api_key_configuration():
    manifest = PluginManifest(
        plugin_id="example.simple",
        display_name="Simple Plugin",
        version="1.0.0",
        description="Minimal API-key configuration test.",
        capabilities=(
            CapabilitySpec(
                name="ping",
                description="Return a ping result.",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object", "properties": {}},
            ),
        ),
    )
    registry = PluginRegistry()
    registry.register(manifest)
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    manager = APIKeyManager()
    with pytest.raises(ValueError, match="either api_keys or api_key_authenticator"):
        create_app(
            registry,
            executor,
            {VALID_API_KEY: ExecutionPrincipal(subject_id="legacy-user")},
            api_key_authenticator=ManagedAPIKeyAuthenticator(manager),
        )
