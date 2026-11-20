"""Deterministic, sequential workflow execution over registered capabilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from universal_automation.core.execution import CapabilityExecutor, ExecutionRequest
from universal_automation.core.registry import CapabilityNotFoundError, PluginNotFoundError
from universal_automation.security import ApprovalGrant, ExecutionPrincipal
from universal_automation.workflows.contracts import (
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowExecutionResult,
    WorkflowInputMapping,
    WorkflowStep,
    WorkflowStepResult,
)

_MISSING = object()


class WorkflowError(RuntimeError):
    """Base exception for workflow validation and execution errors."""


class WorkflowValidationError(WorkflowError):
    """Raised when a workflow references unavailable capabilities."""


class WorkflowInputMappingError(WorkflowError):
    """Raised when a workflow input mapping cannot be resolved safely."""


class WorkflowRunner:
    """Execute versioned workflows using the shared authorization-aware executor.

    Execution is synchronous and sequential. Each capability and compensation
    action passes through CapabilityExecutor independently. Runs are in-memory;
    no queue, persistence, parallelism, or automatic retry is provided.
    """

    def __init__(self, executor: CapabilityExecutor) -> None:
        self._executor = executor
        self._registry = executor.plugin_registry

    def validate(self, workflow: WorkflowDefinition) -> None:
        """Resolve all declared actions before any workflow side effect occurs."""
        if not isinstance(workflow, WorkflowDefinition):
            raise TypeError("workflow must be a validated WorkflowDefinition")

        try:
            for step in workflow.steps:
                self._registry.get_capability(step.plugin_id, step.capability_name)
                if step.compensation is not None:
                    self._registry.get_capability(
                        step.compensation.plugin_id,
                        step.compensation.capability_name,
                    )
        except (PluginNotFoundError, CapabilityNotFoundError) as exc:
            raise WorkflowValidationError(
                "Workflow references an unavailable capability"
            ) from exc

    def execute(
        self,
        workflow: WorkflowDefinition,
        principal: ExecutionPrincipal,
        run_id: str,
        *,
        approvals: Mapping[str, ApprovalGrant] | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> WorkflowExecutionResult:
        """Run steps in order, stopping on failure and compensating in reverse order.

        Approval keys are step IDs. Compensation approvals use the key
        '<step_id>:compensation'. Grants must be bound to the generated request ID.
        """
        self.validate(workflow)
        if not isinstance(principal, ExecutionPrincipal):
            raise TypeError("principal must be a trusted ExecutionPrincipal")
        if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 120:
            raise ValueError("run_id must be a non-empty string of at most 120 characters")

        approval_map = dict(approvals or {})
        started_at = datetime.now(UTC)
        timer_started = perf_counter()
        events: list[WorkflowEvent] = []
        step_results: list[WorkflowStepResult] = []
        result_indices: dict[str, int] = {}
        outputs: dict[str, dict[str, Any]] = {}
        successful_steps: list[WorkflowStep] = []

        self._event(events, "queued")
        self._event(events, "running")
        final_status = "succeeded"

        for step in workflow.steps:
            if cancellation_check is not None and cancellation_check():
                final_status = "cancelled"
                self._compensate(
                    successful_steps,
                    outputs,
                    step_results,
                    result_indices,
                    principal,
                    run_id,
                    approval_map,
                    events,
                )
                break

            if step.condition is not None and not self._condition_matches(
                step.condition, outputs
            ):
                result_indices[step.step_id] = len(step_results)
                step_results.append(
                    WorkflowStepResult(step_id=step.step_id, status="skipped")
                )
                self._event(events, "step_skipped", step.step_id)
                continue

            self._event(events, "step_running", step.step_id)
            try:
                input_data = self._apply_mappings(step.input_data, step.mappings, outputs)
                request = ExecutionRequest(
                    request_id=f"{run_id}:{step.step_id}",
                    plugin_id=step.plugin_id,
                    capability_name=step.capability_name,
                    input_data=input_data,
                )
                result = self._executor.execute(
                    request,
                    principal,
                    approval_map.get(step.step_id),
                )
            except Exception as exc:
                result_indices[step.step_id] = len(step_results)
                step_results.append(
                    WorkflowStepResult(
                        step_id=step.step_id,
                        status="failed",
                        error_code=type(exc).__name__,
                    )
                )
                self._event(events, "step_failed", step.step_id)
                final_status = "failed"
                self._compensate(
                    successful_steps,
                    outputs,
                    step_results,
                    result_indices,
                    principal,
                    run_id,
                    approval_map,
                    events,
                )
                break

            outputs[step.step_id] = result.output_data
            result_indices[step.step_id] = len(step_results)
            step_results.append(
                WorkflowStepResult(
                    step_id=step.step_id,
                    status="succeeded",
                    output_data=result.output_data,
                )
            )
            successful_steps.append(step)
            self._event(events, "step_succeeded", step.step_id)

        self._event(events, final_status)
        completed_at = datetime.now(UTC)
        return WorkflowExecutionResult(
            workflow_id=workflow.workflow_id,
            workflow_version=workflow.version,
            run_id=run_id,
            status=final_status,
            step_results=tuple(step_results),
            events=tuple(events),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=(perf_counter() - timer_started) * 1000,
        )

    def _compensate(
        self,
        successful_steps: list[WorkflowStep],
        outputs: dict[str, dict[str, Any]],
        step_results: list[WorkflowStepResult],
        result_indices: dict[str, int],
        principal: ExecutionPrincipal,
        run_id: str,
        approvals: Mapping[str, ApprovalGrant],
        events: list[WorkflowEvent],
    ) -> None:
        for step in reversed(successful_steps):
            compensation = step.compensation
            if compensation is None:
                continue

            self._event(events, "compensation_running", step.step_id)
            try:
                input_data = self._apply_mappings(
                    compensation.input_data,
                    compensation.mappings,
                    outputs,
                )
                request = ExecutionRequest(
                    request_id=f"{run_id}:{step.step_id}:compensate",
                    plugin_id=compensation.plugin_id,
                    capability_name=compensation.capability_name,
                    input_data=input_data,
                )
                self._executor.execute(
                    request,
                    principal,
                    approvals.get(f"{step.step_id}:compensation"),
                )
            except Exception as exc:
                index = result_indices[step.step_id]
                step_results[index] = step_results[index].model_copy(
                    update={
                        "status": "compensation_failed",
                        "compensation_error_code": type(exc).__name__,
                    }
                )
                self._event(events, "compensation_failed", step.step_id)
            else:
                index = result_indices[step.step_id]
                step_results[index] = step_results[index].model_copy(
                    update={"status": "compensated"}
                )
                self._event(events, "compensation_succeeded", step.step_id)

    @staticmethod
    def _event(
        events: list[WorkflowEvent],
        event_type: WorkflowEventType,
        step_id: str | None = None,
    ) -> None:
        events.append(
            WorkflowEvent(
                event_type=event_type,
                step_id=step_id,
                occurred_at=datetime.now(UTC),
            )
        )

    @classmethod
    def _apply_mappings(
        cls,
        base_input: dict[str, Any],
        mappings: tuple[WorkflowInputMapping, ...],
        outputs: Mapping[str, dict[str, Any]],
    ) -> dict[str, Any]:
        result = deepcopy(base_input)
        for mapping in mappings:
            source = outputs.get(mapping.source_step_id, _MISSING)
            if source is _MISSING:
                raise WorkflowInputMappingError(
                    "Mapped source step has no successful output"
                )
            value = cls._get_path(source, mapping.source_path)
            if value is _MISSING:
                raise WorkflowInputMappingError(
                    "Mapped source output path does not exist"
                )
            cls._set_path(result, mapping.target_path, deepcopy(value))
        return result

    @staticmethod
    def _get_path(source: Any, path: str) -> Any:
        current = source
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                return _MISSING
            current = current[segment]
        return current

    @staticmethod
    def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
        segments = path.split(".")
        current = target
        for segment in segments[:-1]:
            existing = current.get(segment)
            if existing is None:
                existing = {}
                current[segment] = existing
            if not isinstance(existing, dict):
                raise WorkflowInputMappingError(
                    "Mapped target path conflicts with a non-object input value"
                )
            current = existing
        current[segments[-1]] = value

    @classmethod
    def _condition_matches(
        cls,
        condition: WorkflowCondition,
        outputs: Mapping[str, dict[str, Any]],
    ) -> bool:
        source = outputs.get(condition.source_step_id, _MISSING)
        value = (
            _MISSING
            if source is _MISSING
            else cls._get_path(source, condition.source_path)
        )
        if condition.operator == "exists":
            return value is not _MISSING
        if condition.operator == "not_exists":
            return value is _MISSING
        if value is _MISSING:
            return False
        if condition.operator == "equals":
            return value == condition.value
        if condition.operator == "not_equals":
            return value != condition.value
        if condition.operator == "truthy":
            return bool(value)
        if condition.operator == "falsy":
            return not bool(value)
        return False
