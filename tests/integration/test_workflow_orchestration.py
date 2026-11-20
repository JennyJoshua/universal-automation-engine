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
