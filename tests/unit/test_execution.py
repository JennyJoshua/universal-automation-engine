"""Tests for controlled capability execution."""

from typing import Any

import pytest

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import (
    CapabilityExecutor,
    ExecutionRequest,
    HandlerAlreadyRegisteredError,
    HandlerExecutionError,
    HandlerNotRegisteredError,
    InputValidationError,
    OutputValidationError,
)
from universal_automation.core.registry import PluginNotFoundError, PluginRegistry
from universal_automation.security import (
    ApprovalGrant,
    ApprovalRequiredError,
    AuthorizationPolicy,
    ExecutionPrincipal,
    InsufficientPermissionsError,
)


def make_system(*, approval_required: bool = False):
    manifest = PluginManifest(
        plugin_id="example.text-tools",
        display_name="Example Text Tools",
        version="1.0.0",
        description="Text processing capabilities for executor tests.",
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
    return registry, executor


def make_principal() -> ExecutionPrincipal:
    return ExecutionPrincipal(subject_id="user-123", permissions={"text.process"})


def make_request(input_data: dict[str, Any] | None = None) -> ExecutionRequest:
    return ExecutionRequest(
        request_id="request-456",
        plugin_id="example.text-tools",
        capability_name="normalize_text",
        input_data=input_data or {"text": "  Hello  "},
    )


def make_approval() -> ApprovalGrant:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    return ApprovalGrant(
        approval_id="approval-789",
        subject_id="user-123",
        plugin_id="example.text-tools",
        capability_name="normalize_text",
        request_id="request-456",
        approved_at=now - timedelta(seconds=5),
        expires_at=now + timedelta(minutes=5),
    )


def test_register_and_execute_handler() -> None:
    _, executor = make_system()
    executor.register_handler(
        "example.text-tools",
        "normalize_text",
        lambda data: {"normalized": data["text"].strip().lower()},
    )

    result = executor.execute(make_request(), make_principal())

    assert result.output_data == {"normalized": "hello"}
    assert result.plugin_id == "example.text-tools"
    assert result.plugin_version == "1.0.0"
    assert result.duration_ms >= 0


def test_handler_registration_requires_existing_capability() -> None:
    _, executor = make_system()

    with pytest.raises(PluginNotFoundError):
        executor.register_handler("missing.plugin", "missing_action", lambda data: data)


def test_identical_handler_registration_is_idempotent() -> None:
    _, executor = make_system()
    def handler(data: dict[str, Any]) -> dict[str, Any]:
        return {"normalized": data["text"]}

    executor.register_handler("example.text-tools", "normalize_text", handler)
    executor.register_handler("example.text-tools", "normalize_text", handler)


def test_conflicting_handler_registration_is_rejected() -> None:
    _, executor = make_system()
    def first(data: dict[str, Any]) -> dict[str, Any]:
        return {"normalized": data["text"]}

    def second(data: dict[str, Any]) -> dict[str, Any]:
        return {"normalized": data["text"].strip()}

    executor.register_handler("example.text-tools", "normalize_text", first)

    with pytest.raises(HandlerAlreadyRegisteredError):
        executor.register_handler("example.text-tools", "normalize_text", second)


def test_missing_handler_is_rejected() -> None:
    _, executor = make_system()

    with pytest.raises(HandlerNotRegisteredError):
        executor.execute(make_request(), make_principal())


def test_invalid_input_does_not_reach_handler() -> None:
    _, executor = make_system()
    called = False

    def handler(data: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"normalized": "unexpected"}

    executor.register_handler("example.text-tools", "normalize_text", handler)

    with pytest.raises(InputValidationError):
        executor.execute(make_request({"text": 123}), make_principal())

    assert called is False


def test_missing_permission_prevents_handler_invocation() -> None:
    _, executor = make_system()
    called = False

    def handler(data: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"normalized": "unexpected"}

    executor.register_handler("example.text-tools", "normalize_text", handler)

    with pytest.raises(InsufficientPermissionsError):
        executor.execute(
            make_request(),
            ExecutionPrincipal(subject_id="user-123"),
        )

    assert called is False


def test_required_approval_is_checked_before_handler_invocation() -> None:
    _, executor = make_system(approval_required=True)
    called = False

    def handler(data: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"normalized": "unexpected"}

    executor.register_handler("example.text-tools", "normalize_text", handler)

    with pytest.raises(ApprovalRequiredError):
        executor.execute(make_request(), make_principal())

    assert called is False


def test_matching_approval_allows_approval_required_execution() -> None:
    _, executor = make_system(approval_required=True)
    executor.register_handler(
        "example.text-tools",
        "normalize_text",
        lambda data: {"normalized": data["text"].strip()},
    )

    result = executor.execute(make_request(), make_principal(), make_approval())

    assert result.output_data == {"normalized": "Hello"}


def test_invalid_handler_output_is_rejected() -> None:
    _, executor = make_system()
    executor.register_handler(
        "example.text-tools",
        "normalize_text",
        lambda data: {"wrong_field": "value"},
    )

    with pytest.raises(OutputValidationError):
        executor.execute(make_request(), make_principal())


def test_non_object_handler_output_is_rejected() -> None:
    _, executor = make_system()
    executor.register_handler(
        "example.text-tools",
        "normalize_text",
        lambda data: ["not", "an", "object"],  # type: ignore[return-value]
    )

    with pytest.raises(OutputValidationError):
        executor.execute(make_request(), make_principal())


def test_handler_exception_is_wrapped_without_leaking_message() -> None:
    _, executor = make_system()

    def failing_handler(data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("private internal detail")

    executor.register_handler("example.text-tools", "normalize_text", failing_handler)

    with pytest.raises(HandlerExecutionError) as error:
        executor.execute(make_request(), make_principal())

    assert str(error.value) == "Capability handler failed"
    assert isinstance(error.value.__cause__, RuntimeError)
    assert "private internal detail" not in str(error.value)


def test_handler_cannot_mutate_callers_input_data() -> None:
    _, executor = make_system()

    def handler(data: dict[str, Any]) -> dict[str, Any]:
        data["text"] = "changed"
        return {"normalized": "changed"}

    executor.register_handler("example.text-tools", "normalize_text", handler)
    request = make_request({"text": "original"})

    executor.execute(request, make_principal())

    assert request.input_data["text"] == "original"


def test_result_is_defensively_copied_from_handler_output() -> None:
    _, executor = make_system()
    shared_output = {"normalized": "stable"}

    executor.register_handler(
        "example.text-tools",
        "normalize_text",
        lambda data: shared_output,
    )
    result = executor.execute(make_request(), make_principal())

    shared_output["normalized"] = "mutated"

    assert result.output_data["normalized"] == "stable"


def test_non_json_serializable_handler_output_is_rejected() -> None:
    _, executor = make_system()
    executor.register_handler(
        "example.text-tools",
        "normalize_text",
        lambda data: {"normalized": object()},
    )

    with pytest.raises(OutputValidationError):
        executor.execute(make_request(), make_principal())
