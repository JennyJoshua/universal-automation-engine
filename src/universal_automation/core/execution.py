"""Controlled, synchronous execution for explicitly registered capability handlers."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from threading import RLock
from typing import Any, Callable

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field
from referencing import Registry

from universal_automation.core.registry import PluginRegistry
from universal_automation.security import (
    ApprovalGrant,
    AuthorizationPolicy,
    ExecutionPrincipal,
)


class ExecutionModel(BaseModel):
    """Base class for immutable execution request and result envelopes."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExecutionRequest(ExecutionModel):
    """One request to invoke a registered plugin capability."""

    request_id: str = Field(min_length=1, max_length=200)
    plugin_id: str = Field(min_length=1, max_length=100)
    capability_name: str = Field(min_length=1, max_length=64)
    input_data: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(ExecutionModel):
    """Successful result returned by a capability handler."""

    request_id: str
    plugin_id: str
    plugin_version: str
    capability_name: str
    output_data: dict[str, Any]
    duration_ms: float = Field(ge=0)
    completed_at: datetime


class ExecutionError(RuntimeError):
    """Base exception for capability execution failures."""


class HandlerAlreadyRegisteredError(ExecutionError):
    """Raised when a different handler is already bound to a capability."""


class HandlerNotRegisteredError(ExecutionError):
    """Raised when a capability has no trusted in-process handler."""


class InputValidationError(ExecutionError):
    """Raised when request input does not satisfy the declared JSON Schema."""

    def __init__(self, path: tuple[str, ...] = ()) -> None:
        self.path = path
        super().__init__("Capability input does not satisfy its declared schema")


class OutputValidationError(ExecutionError):
    """Raised when a handler result does not satisfy its declared JSON Schema."""

    def __init__(self, path: tuple[str, ...] = ()) -> None:
        self.path = path
        super().__init__("Capability output does not satisfy its declared schema")


class HandlerExecutionError(ExecutionError):
    """Raised when a trusted capability handler fails."""

    def __init__(self) -> None:
        super().__init__("Capability handler failed")


CapabilityHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _HandlerBinding:
    plugin_id: str
    capability_name: str
    handler: CapabilityHandler


class CapabilityExecutor:
    """Authorize and invoke explicitly registered trusted Python callables.

    This initial executor is synchronous and in-process. It does not import plugin
    packages, execute user-supplied code, or provide a sandbox or hard timeout.
    """

    def __init__(
        self,
        plugin_registry: PluginRegistry,
        authorization_policy: AuthorizationPolicy,
    ) -> None:
        self._plugin_registry = plugin_registry
        self._authorization_policy = authorization_policy
        self._handlers: dict[tuple[str, str], _HandlerBinding] = {}
        self._lock = RLock()

    def register_handler(
        self,
        plugin_id: str,
        capability_name: str,
        handler: CapabilityHandler,
    ) -> None:
        """Bind trusted application code to an already registered capability."""
        self._plugin_registry.get_capability(plugin_id, capability_name)
        if not callable(handler):
            raise TypeError("handler must be a callable Python function")

        key = (plugin_id, capability_name)
        with self._lock:
            existing = self._handlers.get(key)
            if existing is not None:
                if existing.handler is handler:
                    return
                raise HandlerAlreadyRegisteredError(
                    f"A handler is already registered for '{plugin_id}.{capability_name}'"
                )
            self._handlers[key] = _HandlerBinding(plugin_id, capability_name, handler)

    def execute(
        self,
        request: ExecutionRequest,
        principal: ExecutionPrincipal,
        approval: ApprovalGrant | None = None,
    ) -> ExecutionResult:
        """Authorize, validate, invoke, and validate one capability request."""
        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be an ExecutionRequest")

        registered = self._plugin_registry.get_capability(
            request.plugin_id,
            request.capability_name,
        )
        self._authorization_policy.authorize(
            principal,
            registered,
            request.request_id,
            approval,
        )

        key = (request.plugin_id, request.capability_name)
        with self._lock:
            binding = self._handlers.get(key)
        if binding is None:
            raise HandlerNotRegisteredError(
                f"No handler is registered for '{request.plugin_id}.{request.capability_name}'"
            )

        input_data = deepcopy(request.input_data)
        self._validate_payload(
            input_data,
            registered.capability.input_schema,
            error_type=InputValidationError,
        )

        started = perf_counter()
        try:
            output_data = binding.handler(input_data)
        except Exception as exc:
            raise HandlerExecutionError() from exc

        duration_ms = (perf_counter() - started) * 1000

        if not isinstance(output_data, dict):
            raise OutputValidationError()

        output_copy = deepcopy(output_data)
        self._validate_payload(
            output_copy,
            registered.capability.output_schema,
            error_type=OutputValidationError,
        )

        return ExecutionResult(
            request_id=request.request_id,
            plugin_id=registered.plugin_id,
            plugin_version=registered.plugin_version,
            capability_name=registered.capability.name,
            output_data=output_copy,
            duration_ms=duration_ms,
            completed_at=datetime.now(UTC),
        )

    @staticmethod
    def _validate_payload(
        payload: dict[str, Any],
        schema: dict[str, Any],
        *,
        error_type: type[InputValidationError] | type[OutputValidationError],
    ) -> None:
        try:
            json.dumps(payload, allow_nan=False)
            validator_class = validator_for(schema)
            validator = validator_class(schema, registry=Registry())
            validator.validate(payload)
        except JsonSchemaValidationError as exc:
            path = tuple(str(part) for part in exc.absolute_path)
            raise error_type(path) from exc
        except (TypeError, ValueError) as exc:
            raise error_type() from exc
