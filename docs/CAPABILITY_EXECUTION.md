# Capability Execution

## Purpose

`CapabilityExecutor` connects the plugin registry, authorization policy, JSON Schema validation, and explicitly registered capability handlers. It is transport-independent and can be called by future REST or MCP adapters.

## Registering a trusted handler

Handlers are ordinary synchronous Python callables registered by trusted application code. A handler can only be bound to a capability already declared in the plugin registry.

```python
from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.security import AuthorizationPolicy

registry = PluginRegistry()
# Register a validated PluginManifest before binding handlers.

executor = CapabilityExecutor(registry, AuthorizationPolicy())

def normalize_text(data: dict[str, object]) -> dict[str, object]:
    value = data["text"]
    if not isinstance(value, str):
        raise TypeError("text must be a string")
    return {"normalized": value.strip().lower()}

executor.register_handler("example.text-tools", "normalize_text", normalize_text)
```

## Executing a capability

```python
from universal_automation.core.execution import ExecutionRequest
from universal_automation.security import ExecutionPrincipal

request = ExecutionRequest(
    request_id="request-456",
    plugin_id="example.text-tools",
    capability_name="normalize_text",
    input_data={"text": "  Hello  "},
)

principal = ExecutionPrincipal(
    subject_id="user-123",
    permissions={"text.process"},
)

result = executor.execute(request, principal)
```

For approval-required capabilities, the host must also supply an `ApprovalGrant` created by a trusted approval workflow.

## Execution lifecycle

1. Resolve the plugin capability from the registry.
2. Enforce the trusted principal's permissions and any request-scoped approval.
3. Resolve the explicitly registered handler.
4. Deep-copy and validate input against the declared JSON Schema.
5. Invoke the synchronous handler.
6. Validate the handler's output against the declared output schema.
7. Return a typed result with plugin version and handler duration.

Invalid input is rejected before the handler is called. Handler exceptions are wrapped in `HandlerExecutionError`; the public error message does not include internal exception details. The original exception remains available as the chained cause for trusted diagnostics.

## JSON Schema safety

The executor uses a local-only schema registry and never retrieves remote schema resources. Plugin contract validation rejects remote `$ref`, `$dynamicRef`, and `$recursiveRef` values. Local references may be used within a schema document.

Input and output values must be JSON-serializable and satisfy their declared schemas.

## Security limitations

- Only trusted in-process Python callables may be registered.
- Registering a handler is not a plugin installation mechanism.
- No third-party code is dynamically imported or loaded.
- The executor is synchronous and has no hard timeout.
- It does not sandbox handlers or isolate their process memory.
- Do not register untrusted plugin code.
- The host application must construct the trusted `ExecutionPrincipal` and `ApprovalGrant`.
- This version does not provide a persistent task queue, execution history, or audit store.

A future isolated worker implementation is required before supporting untrusted third-party code or long-running tasks.
