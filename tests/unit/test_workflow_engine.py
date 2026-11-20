"""Unit and integration-style tests for deterministic workflow execution."""

from datetime import UTC, datetime, timedelta

import pytest

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import (
    CapabilityExecutor,
    HandlerInputError,
)
from universal_automation.core.registry import PluginRegistry
from universal_automation.security import (
    ApprovalGrant,
    ApprovalRequiredError,
    AuthorizationPolicy,
    ExecutionPrincipal,
    InsufficientPermissionsError,
)
from universal_automation.workflows import (
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowInputMapping,
    WorkflowRunner,
    WorkflowStep,
    WorkflowValidationError,
)


def schema(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def make_system():
    calls = []
    capabilities = (
        CapabilitySpec(
            name="create_order",
            description="Create an order.",
            input_schema=schema({"customer": schema({"email": {"type": "string"}}, ["email"])}, ["customer"]),
            output_schema=schema(
                {
                    "order_id": {"type": "string"},
                    "notify": {"type": "boolean"},
                },
                ["order_id", "notify"],
            ),
            permissions=("orders.create",),
        ),
        CapabilitySpec(
            name="send_notice",
            description="Send an order notice.",
            input_schema=schema(
                {"order_id": {"type": "string"}, "payload": schema({"channel": {"type": "string"}})},
                ["order_id"],
            ),
            output_schema=schema({"sent": {"type": "boolean"}}, ["sent"]),
            permissions=("notifications.send",),
        ),
        CapabilitySpec(
            name="cancel_order",
            description="Cancel an order.",
            input_schema=schema({"order_id": {"type": "string"}}, ["order_id"]),
            output_schema=schema({"cancelled": {"type": "boolean"}}, ["cancelled"]),
            permissions=("orders.cancel",),
        ),
        CapabilitySpec(
            name="reserve_stock",
            description="Reserve inventory.",
            input_schema=schema({"order_id": {"type": "string"}}, ["order_id"]),
            output_schema=schema({"reservation_id": {"type": "string"}}, ["reservation_id"]),
            permissions=("inventory.reserve",),
        ),
        CapabilitySpec(
            name="release_stock",
            description="Release inventory reservation.",
            input_schema=schema({"reservation_id": {"type": "string"}}, ["reservation_id"]),
            output_schema=schema({"released": {"type": "boolean"}}, ["released"]),
            permissions=("inventory.release",),
        ),
        CapabilitySpec(
            name="fail_action",
            description="Fail deliberately for workflow tests.",
            input_schema=schema({}),
            output_schema=schema({"ok": {"type": "boolean"}}, ["ok"]),
            permissions=("workflow.test",),
        ),
        CapabilitySpec(
            name="approved_action",
            description="An action that requires request-bound approval.",
            input_schema=schema({}),
            output_schema=schema({"approved": {"type": "boolean"}}, ["approved"]),
            permissions=("reports.approve",),
            approval_required=True,
        ),
    )
    manifest = PluginManifest(
        plugin_id="example.workflow-tools",
        display_name="Workflow Test Tools",
        version="1.0.0",
        description="Capabilities for workflow tests.",
        capabilities=capabilities,
    )
    registry = PluginRegistry()
    registry.register(manifest)
    executor = CapabilityExecutor(registry, AuthorizationPolicy())

    def create_order(data):
        calls.append(("create_order", data))
        return {"order_id": "ORD-1", "notify": data["customer"]["email"] != "quiet@example.com"}

    def send_notice(data):
        calls.append(("send_notice", data))
        return {"sent": True}

    def cancel_order(data):
        calls.append(("cancel_order", data))
        return {"cancelled": True}

    def reserve_stock(data):
        calls.append(("reserve_stock", data))
        return {"reservation_id": "RSV-1"}

    def release_stock(data):
        calls.append(("release_stock", data))
        return {"released": True}

    def fail_action(data):
        calls.append(("fail_action", data))
        raise HandlerInputError("Deliberate workflow test failure")

    def approved_action(data):
        calls.append(("approved_action", data))
        return {"approved": True}

    handlers = {
        "create_order": create_order,
        "send_notice": send_notice,
        "cancel_order": cancel_order,
        "reserve_stock": reserve_stock,
        "release_stock": release_stock,
        "fail_action": fail_action,
        "approved_action": approved_action,
    }
    for name, handler in handlers.items():
        executor.register_handler("example.workflow-tools", name, handler)

    principal = ExecutionPrincipal(
        subject_id="workflow-user",
        permissions={
            "orders.create",
            "notifications.send",
            "orders.cancel",
            "inventory.reserve",
            "inventory.release",
            "workflow.test",
            "reports.approve",
        },
    )
    return WorkflowRunner(executor), principal, calls


def make_workflow(steps, workflow_id="orders.process"):
    return WorkflowDefinition(
        workflow_id=workflow_id,
        version="1.0.0",
        description="A test workflow.",
        steps=tuple(steps),
    )


def create_step(*, compensation=False, email="buyer@example.com"):
    return WorkflowStep(
        step_id="create",
        plugin_id="example.workflow-tools",
        capability_name="create_order",
        input_data={"customer": {"email": email}},
        compensation=(
            {
                "plugin_id": "example.workflow-tools",
                "capability_name": "cancel_order",
                "mappings": [
                    {
                        "source_step_id": "create",
                        "source_path": "order_id",
                        "target_path": "order_id",
                    }
                ],
            }
            if compensation
            else None
        ),
    )


def test_workflow_executes_steps_and_maps_prior_outputs():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(),
            WorkflowStep(
                step_id="notify",
                plugin_id="example.workflow-tools",
                capability_name="send_notice",
                input_data={"payload": {"channel": "email"}},
                mappings=(
                    WorkflowInputMapping(
                        source_step_id="create",
                        source_path="order_id",
                        target_path="order_id",
                    ),
                ),
                condition=WorkflowCondition(
                    source_step_id="create",
                    source_path="notify",
                    operator="equals",
                    value=True,
                ),
            ),
        ]
    )

    result = runner.execute(workflow, principal, "run-100")

    assert result.status == "succeeded"
    assert [step.status for step in result.step_results] == ["succeeded", "succeeded"]
    assert calls[1] == (
        "send_notice",
        {"payload": {"channel": "email"}, "order_id": "ORD-1"},
    )
    assert result.events[0].event_type == "queued"
    assert result.events[-1].event_type == "succeeded"


def test_false_condition_skips_step_without_calling_handler():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(email="quiet@example.com"),
            WorkflowStep(
                step_id="notify",
                plugin_id="example.workflow-tools",
                capability_name="send_notice",
                input_data={"order_id": "unused"},
                condition=WorkflowCondition(
                    source_step_id="create",
                    source_path="notify",
                    operator="equals",
                    value=True,
                ),
            ),
        ]
    )

    result = runner.execute(workflow, principal, "run-101")

    assert result.status == "succeeded"
    assert [step.status for step in result.step_results] == ["succeeded", "skipped"]
    assert [call[0] for call in calls] == ["create_order"]


def test_missing_prior_output_mapping_fails_workflow_safely():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(email="quiet@example.com"),
            WorkflowStep(
                step_id="notify",
                plugin_id="example.workflow-tools",
                capability_name="send_notice",
                mappings=(
                    WorkflowInputMapping(
                        source_step_id="create",
                        source_path="missing.value",
                        target_path="order_id",
                    ),
                ),
            ),
        ]
    )

    result = runner.execute(workflow, principal, "run-102")

    assert result.status == "failed"
    assert result.step_results[-1].error_code == "WorkflowInputMappingError"
    assert [call[0] for call in calls] == ["create_order"]


def test_failure_stops_later_steps_and_compensates_successful_step():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(compensation=True),
            WorkflowStep(
                step_id="fail",
                plugin_id="example.workflow-tools",
                capability_name="fail_action",
            ),
            WorkflowStep(
                step_id="never",
                plugin_id="example.workflow-tools",
                capability_name="send_notice",
                input_data={"order_id": "ORD-1"},
            ),
        ]
    )

    result = runner.execute(workflow, principal, "run-103")

    assert result.status == "failed"
    assert [call[0] for call in calls] == ["create_order", "fail_action", "cancel_order"]
    assert [step.status for step in result.step_results] == [
        "compensated",
        "failed",
    ]
    assert result.step_results[1].error_code == "HandlerInputError"
    assert result.events[-2].event_type == "compensation_succeeded"
    assert result.events[-1].event_type == "failed"


def test_multiple_successful_steps_are_compensated_in_reverse_order():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(compensation=True),
            WorkflowStep(
                step_id="reserve",
                plugin_id="example.workflow-tools",
                capability_name="reserve_stock",
                mappings=(
                    WorkflowInputMapping(
                        source_step_id="create",
                        source_path="order_id",
                        target_path="order_id",
                    ),
                ),
                compensation={
                    "plugin_id": "example.workflow-tools",
                    "capability_name": "release_stock",
                    "mappings": [
                        {
                            "source_step_id": "reserve",
                            "source_path": "reservation_id",
                            "target_path": "reservation_id",
                        }
                    ],
                },
            ),
            WorkflowStep(
                step_id="fail",
                plugin_id="example.workflow-tools",
                capability_name="fail_action",
            ),
        ]
    )

    result = runner.execute(workflow, principal, "run-104")

    assert result.status == "failed"
    assert [call[0] for call in calls] == [
        "create_order",
        "reserve_stock",
        "fail_action",
        "release_stock",
        "cancel_order",
    ]
    assert [step.status for step in result.step_results] == [
        "compensated",
        "compensated",
        "failed",
    ]


def test_compensation_failure_is_reported_without_stopping_other_compensations():
    runner, principal, calls = make_system()
    restricted = principal.model_copy(
        update={"permissions": frozenset({"orders.create", "workflow.test"})}
    )
    workflow = make_workflow(
        [
            create_step(compensation=True),
            WorkflowStep(
                step_id="fail",
                plugin_id="example.workflow-tools",
                capability_name="fail_action",
            ),
        ]
    )

    result = runner.execute(workflow, restricted, "run-105")

    assert result.status == "failed"
    assert result.step_results[0].status == "compensation_failed"
    assert result.step_results[0].compensation_error_code == "InsufficientPermissionsError"
    assert [call[0] for call in calls] == ["create_order", "fail_action"]


def test_each_step_is_authorized_independently():
    runner, principal, calls = make_system()
    restricted = principal.model_copy(
        update={"permissions": frozenset({"orders.create"})}
    )
    workflow = make_workflow(
        [
            create_step(),
            WorkflowStep(
                step_id="notify",
                plugin_id="example.workflow-tools",
                capability_name="send_notice",
                input_data={"order_id": "ORD-1"},
            ),
        ]
    )

    result = runner.execute(workflow, restricted, "run-106")

    assert result.status == "failed"
    assert result.step_results[-1].error_code == "InsufficientPermissionsError"
    assert [call[0] for call in calls] == ["create_order"]


def test_approval_is_bound_to_the_workflow_step_request_id():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            WorkflowStep(
                step_id="approved",
                plugin_id="example.workflow-tools",
                capability_name="approved_action",
            )
        ]
    )

    missing = runner.execute(workflow, principal, "run-107")
    assert missing.status == "failed"
    assert missing.step_results[0].error_code == "ApprovalRequiredError"
    assert calls == []

    now = datetime.now(UTC)
    grant = ApprovalGrant(
        approval_id="approval-workflow",
        subject_id=principal.subject_id,
        plugin_id="example.workflow-tools",
        capability_name="approved_action",
        request_id="run-107:approved",
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=2),
    )
    approved = runner.execute(
        workflow,
        principal,
        "run-107",
        approvals={"approved": grant},
    )
    assert approved.status == "succeeded"
    assert calls == [("approved_action", {})]


def test_cancellation_between_steps_triggers_compensation():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(compensation=True),
            WorkflowStep(
                step_id="notify",
                plugin_id="example.workflow-tools",
                capability_name="send_notice",
                input_data={"order_id": "ORD-1"},
            ),
        ]
    )

    result = runner.execute(
        workflow,
        principal,
        "run-108",
        cancellation_check=lambda: len(calls) >= 1,
    )

    assert result.status == "cancelled"
    assert [call[0] for call in calls] == ["create_order", "cancel_order"]
    assert result.step_results[0].status == "compensated"
    assert result.events[-1].event_type == "cancelled"


def test_validation_resolves_all_capabilities_before_side_effects():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(),
            WorkflowStep(
                step_id="missing",
                plugin_id="missing.plugin",
                capability_name="missing_action",
            ),
        ]
    )

    with pytest.raises(WorkflowValidationError):
        runner.validate(workflow)
    assert calls == []


def test_mapped_target_conflict_fails_before_next_handler():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            create_step(),
            WorkflowStep(
                step_id="notify",
                plugin_id="example.workflow-tools",
                capability_name="send_notice",
                input_data={"payload": "not-an-object"},
                mappings=(
                    WorkflowInputMapping(
                        source_step_id="create",
                        source_path="order_id",
                        target_path="payload.order_id",
                    ),
                ),
            ),
        ]
    )

    result = runner.execute(workflow, principal, "run-109")

    assert result.status == "failed"
    assert result.step_results[-1].error_code == "WorkflowInputMappingError"
    assert [call[0] for call in calls] == ["create_order"]



def test_preflight_rejects_declared_capability_without_handler():
    registry = PluginRegistry()
    manifest = PluginManifest(
        plugin_id="example.unbound",
        display_name="Unbound Capability",
        version="1.0.0",
        description="A declared capability with no handler.",
        capabilities=(
            CapabilitySpec(
                name="do_work",
                description="Do work.",
                input_schema=schema({}),
                output_schema=schema({"ok": {"type": "boolean"}}, ["ok"]),
            ),
        ),
    )
    registry.register(manifest)
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    runner = WorkflowRunner(executor)
    workflow = WorkflowDefinition(
        workflow_id="preflight.check",
        version="1.0.0",
        description="Ensure all handlers are bound before execution.",
        steps=(
            WorkflowStep(
                step_id="work",
                plugin_id="example.unbound",
                capability_name="do_work",
            ),
        ),
    )

    with pytest.raises(WorkflowValidationError, match="without a registered handler"):
        runner.validate(workflow)


def test_run_id_length_is_bounded():
    runner, principal, _ = make_system()
    workflow = make_workflow([create_step()])
    with pytest.raises(ValueError, match="120 characters"):
        runner.execute(workflow, principal, "x" * 121)


def test_failed_handler_is_not_retried_automatically():
    runner, principal, calls = make_system()
    workflow = make_workflow(
        [
            WorkflowStep(
                step_id="fail",
                plugin_id="example.workflow-tools",
                capability_name="fail_action",
            )
        ]
    )

    result = runner.execute(workflow, principal, "run-110")

    assert result.status == "failed"
    assert len(calls) == 1
