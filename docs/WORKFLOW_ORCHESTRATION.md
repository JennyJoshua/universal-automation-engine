# Workflow Orchestration

## Purpose and scope

The workflow engine combines existing registered capabilities into a versioned, sequential workflow. It is transport-independent and uses the same CapabilityExecutor that REST and MCP adapters use.

The first implementation is intentionally synchronous and in-memory. It does not provide a background queue, persistence, parallel branches, schedules, distributed execution, or automatic retries.

## Define a workflow

~~~python
from universal_automation.workflows import (
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowInputMapping,
    WorkflowRunner,
    WorkflowStep,
)

workflow = WorkflowDefinition(
    workflow_id="orders.process",
    version="1.0.0",
    description="Create an order and notify the customer.",
    steps=(
        WorkflowStep(
            step_id="create",
            plugin_id="example.order-tools",
            capability_name="create_order",
            input_data={"customer": {"email": "customer@example.com"}},
        ),
        WorkflowStep(
            step_id="notify",
            plugin_id="example.notification-tools",
            capability_name="send_notice",
            input_data={"channel": "email"},
            mappings=(
                WorkflowInputMapping(
                    source_step_id="create",
                    source_path="order_id",
                    target_path="order_id",
                ),
            ),
            condition=WorkflowCondition(
                source_step_id="create",
                source_path="notify_customer",
                operator="equals",
                value=True,
            ),
        ),
    ),
)

runner = WorkflowRunner(executor)
result = runner.execute(workflow, principal, run_id="orders-run-001")
~~~

Every step names an already registered plugin and capability. Static input_data supplies fixed values. Mappings copy a value from an earlier step's output_data into a nested input field.

Mapping paths address object keys only; they do not evaluate expressions or index arbitrary Python objects. A mapping source must exist and have completed successfully. Missing source data fails the workflow safely.

## Conditional branching

A condition can inspect one field from an earlier step and use one of these operators:

- exists / not_exists
- equals / not_equals
- truthy / falsy

Conditions cannot execute code, call functions, access environment variables, or read arbitrary files. A false condition marks the step as skipped. A missing value is false for comparisons and truthiness checks; not_exists is true when the source path is absent.

## State and failure semantics

Workflow run states are queued, running, succeeded, failed, and cancelled. The returned result includes a bounded event sequence and per-step results.

Step outcomes include succeeded, skipped, failed, compensated, and compensation_failed.

- Steps execute in declared order; parallel execution is not supported.
- The first failed step stops the workflow. Later steps are not attempted.
- The workflow does not automatically retry failed capabilities.
- A host may supply a cancellation callback; it is checked between steps, not during a running handler.
- When a step fails or cancellation is observed, successful earlier steps with compensation actions are compensated in reverse order.
- Compensation is best-effort. A compensation failure is recorded, and remaining compensations are still attempted.
- Each normal step and compensation action is independently authorized by CapabilityExecutor.

## Compensation

A step may declare one compensation capability. Its mappings may use outputs from earlier steps and the step being compensated. Compensation is not guaranteed to restore external state; capability authors must implement safe, idempotent undo behavior appropriate to their resource.

Approval grants are supplied by the trusted host using keys matching the step ID. Compensation approvals use the key "<step_id>:compensation". Each grant must be bound to the generated request ID:

- Normal step: "<run_id>:<step_id>"
- Compensation: "<run_id>:<step_id>:compensate"

Do not construct approval grants from client-supplied booleans or claims. Use the trusted host approval workflow.

## Limits and validation

- Maximum 50 steps per workflow.
- Maximum 50 input mappings per step.
- Maximum 10 object-key segments per mapping/condition path.
- Maximum workflow definition size: 1 MiB.
- Step IDs must be unique.
- Conditions and normal input mappings may reference only earlier steps.
- Compensation mappings may reference earlier steps or their own step.
- These backward-only references make dependency cycles impossible.
- All referenced plugin capabilities are resolved before the first workflow side effect.
- Each mapped input is still validated against the target capability's declared JSON Schema.

## Security and operational limitations

The same trusted ExecutionPrincipal is passed to the executor for every step. Each capability independently enforces its own permissions and approval requirements. A workflow cannot grant itself permissions or bypass capability authorization.

Runs are synchronous and in-memory. The result is returned to the caller; it is not persisted. A cancellation callback is cooperative between steps and cannot interrupt a currently running handler. The workflow engine inherits the executor's in-process trust boundary and does not sandbox handlers.

Automatic retries are intentionally disabled until retry-safety and idempotency contracts are designed. Workflow orchestration does not change the existing limitation that handlers have no hard timeout.

## Interfaces

The workflow runner is currently a Python API. Dedicated REST workflow endpoints and MCP workflow tools are deferred to the REST/MCP integration maturity batch. Hosts can expose the runner through their own trusted application layer in the meantime.
