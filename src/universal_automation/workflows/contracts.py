"""Versioned, declarative contracts for deterministic workflows."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_WORKFLOW_ID = re.compile(r"^[a-z][a-z0-9._-]{0,99}$")
_STEP_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*$")

MAX_WORKFLOW_STEPS = 50
MAX_STEP_MAPPINGS = 50
MAX_WORKFLOW_BYTES = 1_048_576
MAX_PATH_DEPTH = 10


class WorkflowContractModel(BaseModel):
    """Immutable contract model that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class WorkflowInputMapping(WorkflowContractModel):
    """Copy one prior step's output value into a nested input field."""

    source_step_id: str = Field(min_length=1, max_length=64)
    source_path: str = Field(min_length=1, max_length=200)
    target_path: str = Field(min_length=1, max_length=200)

    @field_validator("source_path", "target_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        segments = value.split(".")
        if (
            not _PATH.fullmatch(value)
            or len(segments) > MAX_PATH_DEPTH
            or any(segment.startswith("__") for segment in segments)
        ):
            raise ValueError("Workflow paths must use safe object keys with a maximum depth of 10")
        return value


class WorkflowCondition(WorkflowContractModel):
    """A deliberately small condition evaluated against an earlier step output."""

    source_step_id: str = Field(min_length=1, max_length=64)
    source_path: str = Field(min_length=1, max_length=200)
    operator: Literal["exists", "not_exists", "equals", "not_equals", "truthy", "falsy"]
    value: Any = None

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, value: str) -> str:
        segments = value.split(".")
        if (
            not _PATH.fullmatch(value)
            or len(segments) > MAX_PATH_DEPTH
            or any(segment.startswith("__") for segment in segments)
        ):
            raise ValueError("Condition paths must use safe object keys with a maximum depth of 10")
        return value

    @model_validator(mode="after")
    def require_comparison_value(self) -> WorkflowCondition:
        if self.operator in ("equals", "not_equals") and "value" not in self.model_fields_set:
            raise ValueError("equals and not_equals conditions require a value")
        try:
            json.dumps(self.value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Condition values must be JSON-compatible") from exc
        return self


class WorkflowCompensation(WorkflowContractModel):
    """A separately authorized capability to undo one successful step."""

    plugin_id: str = Field(min_length=1, max_length=100)
    capability_name: str = Field(min_length=1, max_length=64)
    input_data: dict[str, Any] = Field(default_factory=dict)
    mappings: tuple[WorkflowInputMapping, ...] = Field(default=(), max_length=MAX_STEP_MAPPINGS)


class WorkflowStep(WorkflowContractModel):
    """One ordered capability invocation in a workflow."""

    contract_version: Literal["1.0"] = "1.0"
    step_id: str = Field(min_length=1, max_length=64)
    plugin_id: str = Field(min_length=1, max_length=100)
    capability_name: str = Field(min_length=1, max_length=64)
    input_data: dict[str, Any] = Field(default_factory=dict)
    mappings: tuple[WorkflowInputMapping, ...] = Field(default=(), max_length=MAX_STEP_MAPPINGS)
    condition: WorkflowCondition | None = None
    compensation: WorkflowCompensation | None = None

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, value: str) -> str:
        if not _STEP_ID.fullmatch(value):
            raise ValueError(
                "Step IDs must start with a lowercase letter and use lowercase letters, digits, "
                "hyphens, or underscores"
            )
        return value

    @model_validator(mode="after")
    def require_unique_mapping_targets(self) -> WorkflowStep:
        targets = [mapping.target_path for mapping in self.mappings]
        if len(targets) != len(set(targets)):
            raise ValueError("Step input mapping target paths must be unique")
        if self.compensation is not None:
            compensation_targets = [
                mapping.target_path for mapping in self.compensation.mappings
            ]
            if len(compensation_targets) != len(set(compensation_targets)):
                raise ValueError("Compensation mapping target paths must be unique")
        return self


class WorkflowDefinition(WorkflowContractModel):
    """A versioned, sequential workflow with bounded references and complexity."""

    workflow_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)
    contract_version: Literal["1.0"] = "1.0"
    description: str = Field(min_length=1, max_length=1000)
    steps: tuple[WorkflowStep, ...] = Field(min_length=1, max_length=MAX_WORKFLOW_STEPS)

    @field_validator("workflow_id")
    @classmethod
    def validate_workflow_id(cls, value: str) -> str:
        if not _WORKFLOW_ID.fullmatch(value):
            raise ValueError("Workflow IDs must be lowercase identifiers")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not _VERSION.fullmatch(value):
            raise ValueError("Workflow version must use MAJOR.MINOR.PATCH")
        return value

    @model_validator(mode="after")
    def validate_references_and_size(self) -> WorkflowDefinition:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Workflow step IDs must be unique")

        previous_steps: set[str] = set()
        total_mappings = 0
        for step in self.steps:
            if step.condition and step.condition.source_step_id not in previous_steps:
                raise ValueError("Workflow conditions may reference only earlier steps")
            for mapping in step.mappings:
                if mapping.source_step_id not in previous_steps:
                    raise ValueError("Step input mappings may reference only earlier steps")
                total_mappings += 1
            if step.compensation:
                allowed_sources = previous_steps | {step.step_id}
                for mapping in step.compensation.mappings:
                    if mapping.source_step_id not in allowed_sources:
                        raise ValueError(
                            "Compensation mappings may reference earlier steps or their own step"
                        )
                    total_mappings += 1
            previous_steps.add(step.step_id)

        if total_mappings > MAX_WORKFLOW_STEPS * MAX_STEP_MAPPINGS:
            raise ValueError("Workflow contains too many input mappings")

        try:
            encoded = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Workflow definition must contain JSON-compatible values") from exc
        if len(encoded.encode("utf-8")) > MAX_WORKFLOW_BYTES:
            raise ValueError("Workflow definition exceeds the 1 MiB size limit")
        return self


WorkflowRunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
WorkflowStepStatus = Literal[
    "running",
    "succeeded",
    "skipped",
    "failed",
    "compensated",
    "compensation_failed",
]
WorkflowEventType = Literal[
    "queued",
    "running",
    "step_running",
    "step_succeeded",
    "step_skipped",
    "step_failed",
    "compensation_running",
    "compensation_succeeded",
    "compensation_failed",
    "succeeded",
    "failed",
    "cancelled",
]


class WorkflowEvent(WorkflowContractModel):
    """A bounded lifecycle event returned with an in-memory workflow run."""

    event_type: WorkflowEventType
    occurred_at: datetime
    step_id: str | None = None


class WorkflowStepResult(WorkflowContractModel):
    """The final outcome for one workflow step."""

    step_id: str
    status: WorkflowStepStatus
    output_data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    compensation_error_code: str | None = None


class WorkflowExecutionResult(WorkflowContractModel):
    """Final workflow state and bounded step/event results."""

    workflow_id: str
    workflow_version: str
    run_id: str
    status: WorkflowRunStatus
    step_results: tuple[WorkflowStepResult, ...]
    events: tuple[WorkflowEvent, ...]
    started_at: datetime
    completed_at: datetime
    duration_ms: float = Field(ge=0)
