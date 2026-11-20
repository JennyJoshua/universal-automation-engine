"""FastAPI application factory for plugin discovery and capability execution."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader

from universal_automation.core.contracts import PluginManifest
from universal_automation.core.execution import (
    CapabilityExecutor,
    ExecutionRequest,
    ExecutionResult,
    HandlerExecutionError,
    HandlerNotRegisteredError,
    InputValidationError,
    OutputValidationError,
)
from universal_automation.core.registry import (
    CapabilityNotFoundError,
    PluginNotFoundError,
    PluginRegistry,
)
from universal_automation.interfaces.api.auth import APIKeyAuthenticator, AuthenticationError
from universal_automation.security import (
    ApprovalRequiredError,
    AuthorizationError,
    ExecutionPrincipal,
    InsufficientPermissionsError,
    InvalidApprovalError,
)


def create_app(
    plugin_registry: PluginRegistry,
    executor: CapabilityExecutor,
    api_keys: Mapping[str, ExecutionPrincipal],
) -> FastAPI:
    """Create an API app using host-provided registry, executor, and API keys."""
    if executor.plugin_registry is not plugin_registry:
        raise ValueError("executor and API must use the same plugin registry instance")

    authenticator = APIKeyAuthenticator(api_keys)
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    app = FastAPI(
        title="Universal Automation Engine API",
        description="Authenticated API for plugin discovery and controlled automation execution.",
        version="0.1.0",
    )

    def require_principal(
        api_key: str | None = Security(api_key_header),
    ) -> ExecutionPrincipal:
        try:
            return authenticator.authenticate(api_key)
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "APIKey"},
            ) from exc

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/plugins", response_model=list[PluginManifest], tags=["plugins"])
    def list_plugins(
        _principal: ExecutionPrincipal = Depends(require_principal),  # noqa: B008  # noqa: B008
    ) -> list[PluginManifest]:
        return list(plugin_registry.list_plugins())

    @app.get("/v1/plugins/{plugin_id}", response_model=PluginManifest, tags=["plugins"])
    def get_plugin(
        plugin_id: str,
        _principal: ExecutionPrincipal = Depends(require_principal),  # noqa: B008
    ) -> PluginManifest:
        try:
            return plugin_registry.get(plugin_id)
        except PluginNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Plugin not found") from exc

    @app.get("/v1/capabilities", tags=["capabilities"])
    def list_capabilities(
        _principal: ExecutionPrincipal = Depends(require_principal),  # noqa: B008
    ) -> list[dict[str, object]]:
        return [
            {
                "plugin_id": item.plugin_id,
                "plugin_version": item.plugin_version,
                "capability": item.capability,
            }
            for item in plugin_registry.list_capabilities()
        ]

    @app.get(
        "/v1/plugins/{plugin_id}/capabilities/{capability_name}",
        tags=["capabilities"],
    )
    def get_capability(
        plugin_id: str,
        capability_name: str,
        _principal: ExecutionPrincipal = Depends(require_principal),  # noqa: B008
    ) -> dict[str, object]:
        try:
            item = plugin_registry.get_capability(plugin_id, capability_name)
        except (PluginNotFoundError, CapabilityNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Capability not found") from exc

        return {
            "plugin_id": item.plugin_id,
            "plugin_version": item.plugin_version,
            "capability": item.capability,
        }

    @app.post(
        "/v1/executions",
        response_model=ExecutionResult,
        tags=["executions"],
    )
    def execute(
        request: ExecutionRequest,
        principal: ExecutionPrincipal = Depends(require_principal),
    ) -> ExecutionResult:
        try:
            return executor.execute(request, principal)
        except (PluginNotFoundError, CapabilityNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Plugin capability not found") from exc
        except (InsufficientPermissionsError, ApprovalRequiredError, InvalidApprovalError) as exc:
            raise HTTPException(status_code=403, detail="Execution is not authorized") from exc
        except InputValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": str(exc), "path": list(exc.path)},
            ) from exc
        except HandlerNotRegisteredError as exc:
            raise HTTPException(
                status_code=409,
                detail="Capability handler is unavailable",
            ) from exc
        except (HandlerExecutionError, OutputValidationError) as exc:
            raise HTTPException(status_code=500, detail="Capability execution failed") from exc
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail="Execution is not authorized") from exc

    return app
