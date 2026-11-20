"""Tests for workflow contracts and bounded validation."""

import pytest
from pydantic import ValidationError

from universal_automation.workflows import (
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowInputMapping,
    WorkflowStep,
)


def step(step_id: str, **overrides) -> WorkflowStep:
    values = {
        "step_id": step_id,
        "plugin_id": "example.workflow-tools",
        "capability_name": "create_order",
        "input_data": {},
    }
    values.update(overrides)
    return WorkflowStep.model_validate(values)


def workflow(steps: tuple[WorkflowStep, ...]) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="orders.process",
        version="1.0.0",
        description="Process an order using registered capabilities.",
        steps=steps,
    )


def test_valid_versioned_workflow_is_accepted():
    definition = workflow(
        (
            step("create"),
            step(
                "notify",
                mappings=(
                    WorkflowInputMapping(
                        source_step_id="create",
                        source_path="order.id",
                        target_path="payload.order_id",
                    ),
                ),
                condition=WorkflowCondition(
                    source_step_id="create",
                    source_path="notify",
                    operator="equals",
                    value=True,
                ),
            ),
        )
    )
    assert definition.contract_version == "1.0"
    assert len(definition.steps) == 2


def test_duplicate_step_ids_are_rejected():
    with pytest.raises(ValidationError, match="unique"):
        workflow((step("create"), step("create")))


def test_forward_references_are_rejected():
    with pytest.raises(ValidationError, match="earlier steps"):
        workflow(
            (
                step(
                    "notify",
                    mappings=(
                        WorkflowInputMapping(
                            source_step_id="create",
                            source_path="order_id",
                            target_path="order_id",
                        ),
                    ),
                ),
                step("create"),
            )
        )


def test_condition_cannot_reference_current_or_future_step():
    with pytest.raises(ValidationError, match="earlier steps"):
        workflow(
            (
                step(
                    "create",
                    condition=WorkflowCondition(
                        source_step_id="create",
                        source_path="ready",
                        operator="truthy",
                    ),
                ),
            )
        )


def test_compensation_may_reference_its_own_step_output():
    definition = workflow(
        (
            step(
                "create",
                compensation={
                    "plugin_id": "example.workflow-tools",
                    "capability_name": "cancel_order",
                    "mappings": [
                        {
                            "source_step_id": "create",
                            "source_path": "order_id",
                            "target_path": "order_id",
                        }
                    ],
                },
            ),
        )
    )
    assert definition.steps[0].compensation is not None


def test_compensation_cannot_reference_a_future_step():
    with pytest.raises(ValidationError, match="earlier steps or their own step"):
        workflow(
            (
                step(
                    "create",
                    compensation={
                        "plugin_id": "example.workflow-tools",
                        "capability_name": "cancel_order",
                        "mappings": [
                            {
                                "source_step_id": "later",
                                "source_path": "order_id",
                                "target_path": "order_id",
                            }
                        ],
                    },
                ),
                step("later"),
            )
        )


def test_equals_condition_requires_explicit_value():
    with pytest.raises(ValidationError, match="require a value"):
        WorkflowCondition(
            source_step_id="create",
            source_path="ready",
            operator="equals",
        )


def test_unsafe_or_excessively_deep_mapping_paths_are_rejected():
    with pytest.raises(ValidationError, match="safe object keys"):
        WorkflowInputMapping(
            source_step_id="create",
            source_path="order.__private",
            target_path="order.id",
        )
    with pytest.raises(ValidationError, match="maximum depth"):
        WorkflowInputMapping(
            source_step_id="create",
            source_path="a.b.c.d.e.f.g.h.i.j.k",
            target_path="order.id",
        )


def test_workflow_step_limit_is_enforced():
    steps = tuple(step(f"step-{index}") for index in range(51))
    with pytest.raises(ValidationError, match="at most 50"):
        workflow(steps)


@pytest.mark.parametrize("version", ["1", "v1.0.0", "01.0.0", "1.0"])
def test_invalid_workflow_versions_are_rejected(version):
    with pytest.raises(ValidationError, match="MAJOR.MINOR.PATCH"):
        WorkflowDefinition(
            workflow_id="orders.process",
            version=version,
            description="Invalid version.",
            steps=(step("create"),),
        )

def test_duplicate_mapping_targets_are_rejected():
    with pytest.raises(ValidationError, match="target paths must be unique"):
        workflow(
            (
                step("create"),
                step(
                    "notify",
                    mappings=(
                        WorkflowInputMapping(
                            source_step_id="create",
                            source_path="order_id",
                            target_path="order_id",
                        ),
                        WorkflowInputMapping(
                            source_step_id="create",
                            source_path="notify",
                            target_path="order_id",
                        ),
                    ),
                ),
            )
        )


def test_step_contract_version_is_explicit():
    assert step("create").contract_version == "1.0"
