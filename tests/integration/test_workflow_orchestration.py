"""End-to-end workflow runner integration tests."""

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.security import AuthorizationPolicy, ExecutionPrincipal
from universal_automation.workflows import (
    WorkflowDefinition,
    WorkflowInputMapping,
    WorkflowRunner,
    WorkflowStep,
)


def test_workflow_runner_composes_registered_capabilities():
    registry = PluginRegistry()
    manifest = PluginManifest(
        plugin_id="example.integration",
        display_name="Integration Capabilities",
        version="1.0.0",
        description="Small workflow integration fixture.",
        capabilities=(
            CapabilitySpec(
                name="make_reference",
                description="Create a reference value.",
                input_schema={
                    "type": "object",
                    "properties": {"prefix": {"type": "string"}},
                    "required": ["prefix"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"reference": {"type": "string"}},
                    "required": ["reference"],
                    "additionalProperties": False,
                },
                permissions=("reference.create",),
            ),
            CapabilitySpec(
                name="consume_reference",
                description="Consume a reference value.",
                input_schema={
                    "type": "object",
                    "properties": {"reference": {"type": "string"}},
                    "required": ["reference"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"accepted": {"type": "boolean"}},
                    "required": ["accepted"],
                    "additionalProperties": False,
                },
                permissions=("reference.consume",),
            ),
        ),
    )
    registry.register(manifest)
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    seen = []
    executor.register_handler(
        "example.integration",
        "make_reference",
        lambda data: {"reference": data["prefix"] + "-001"},
    )

    def consume(data):
        seen.append(data["reference"])
        return {"accepted": True}

    executor.register_handler("example.integration", "consume_reference", consume)
    runner = WorkflowRunner(executor)
    workflow = WorkflowDefinition(
        workflow_id="integration.compose",
        version="1.0.0",
        description="Pass a generated reference to the next capability.",
        steps=(
            WorkflowStep(
                step_id="make",
                plugin_id="example.integration",
                capability_name="make_reference",
                input_data={"prefix": "ORDER"},
            ),
            WorkflowStep(
                step_id="consume",
                plugin_id="example.integration",
                capability_name="consume_reference",
                mappings=(
                    WorkflowInputMapping(
                        source_step_id="make",
                        source_path="reference",
                        target_path="reference",
                    ),
                ),
            ),
        ),
    )
    principal = ExecutionPrincipal(
        subject_id="integration-user",
        permissions={"reference.create", "reference.consume"},
    )

    result = runner.execute(workflow, principal, "integration-run-1")

    assert result.status == "succeeded"
    assert seen == ["ORDER-001"]
    assert [step.status for step in result.step_results] == ["succeeded", "succeeded"]


def test_workflow_failure_runs_compensation_and_stops_remaining_steps():
    registry = PluginRegistry()
    manifest = PluginManifest(
        plugin_id="example.rollback",
        display_name="Rollback Integration Capabilities",
        version="1.0.0",
        description="Failure and compensation integration fixture.",
        capabilities=(
            CapabilitySpec(
                name="create_resource",
                description="Create a resource.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={
                    "type": "object",
                    "properties": {"resource_id": {"type": "string"}},
                    "required": ["resource_id"],
                    "additionalProperties": False,
                },
                permissions=("resource.create",),
            ),
            CapabilitySpec(
                name="remove_resource",
                description="Remove a created resource.",
                input_schema={
                    "type": "object",
                    "properties": {"resource_id": {"type": "string"}},
                    "required": ["resource_id"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"removed": {"type": "boolean"}},
                    "required": ["removed"],
                    "additionalProperties": False,
                },
                permissions=("resource.remove",),
            ),
            CapabilitySpec(
                name="fail_operation",
                description="Fail to trigger compensation.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
                permissions=("operation.run",),
            ),
            CapabilitySpec(
                name="never_run",
                description="A later step that must not run.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
                permissions=("operation.run",),
            ),
        ),
    )
    registry.register(manifest)
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    calls = []

    def create_resource(_data):
        calls.append("create")
        return {"resource_id": "RES-9"}

    def remove_resource(data):
        calls.append(("remove", data["resource_id"]))
        return {"removed": True}

    def fail_operation(_data):
        calls.append("fail")
        raise RuntimeError("internal integration failure")

    def never_run(_data):
        calls.append("never")
        return {"ok": True}

    executor.register_handler("example.rollback", "create_resource", create_resource)
    executor.register_handler("example.rollback", "remove_resource", remove_resource)
    executor.register_handler("example.rollback", "fail_operation", fail_operation)
    executor.register_handler("example.rollback", "never_run", never_run)
    workflow = WorkflowDefinition(
        workflow_id="integration.rollback",
        version="1.0.0",
        description="Compensate a completed step after a later step fails.",
        steps=(
            WorkflowStep(
                step_id="create",
                plugin_id="example.rollback",
                capability_name="create_resource",
                compensation={
                    "plugin_id": "example.rollback",
                    "capability_name": "remove_resource",
                    "mappings": [
                        {
                            "source_step_id": "create",
                            "source_path": "resource_id",
                            "target_path": "resource_id",
                        }
                    ],
                },
            ),
            WorkflowStep(
                step_id="fail",
                plugin_id="example.rollback",
                capability_name="fail_operation",
            ),
            WorkflowStep(
                step_id="never",
                plugin_id="example.rollback",
                capability_name="never_run",
            ),
        ),
    )
    principal = ExecutionPrincipal(
        subject_id="rollback-user",
        permissions={"resource.create", "resource.remove", "operation.run"},
    )

    result = WorkflowRunner(executor).execute(workflow, principal, "rollback-run-1")

    assert result.status == "failed"
    assert calls == ["create", "fail", ("remove", "RES-9")]
    assert [item.status for item in result.step_results] == [
        "compensated",
        "failed",
    ]
