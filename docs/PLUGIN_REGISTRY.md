# Plugin Registry

## Purpose

The in-memory `PluginRegistry` stores validated `PluginManifest` objects and provides deterministic discovery of their declared capabilities. It is independent of REST, MCP, plugin execution, and persistent storage.

## Basic usage

```python
from universal_automation.core import CapabilitySpec, PluginManifest
from universal_automation.core.registry import PluginRegistry

manifest = PluginManifest(
    plugin_id="example.file-tools",
    display_name="Example File Tools",
    version="1.0.0",
    description="Read-only file discovery tools.",
    capabilities=(
        CapabilitySpec(
            name="list_files",
            description="List files in a configured workspace.",
            input_schema={
                "type": "object",
                "properties": {"workspace": {"type": "string"}},
                "required": ["workspace"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {"files": {"type": "array", "items": {"type": "string"}}},
                "required": ["files"],
                "additionalProperties": False,
            },
            permissions=("files.read",),
        ),
    ),
)

registry = PluginRegistry()
registry.register(manifest)

plugin = registry.get("example.file-tools")
capability = registry.get_capability("example.file-tools", "list_files")
all_capabilities = registry.list_capabilities()
```

## Registry behavior

- Registration accepts only validated `PluginManifest` instances.
- Re-registering an identical manifest is idempotent.
- Registering a different manifest under an existing `plugin_id` raises `PluginAlreadyRegisteredError`. A plugin update must be handled explicitly in a future versioning/update workflow.
- Unknown plugin lookups raise `PluginNotFoundError`.
- Unknown capability lookups raise `CapabilityNotFoundError`.
- Plugin and capability listings are sorted deterministically.
- Registry operations are protected by a re-entrant lock.
- Manifests are deep-copied when registered and returned. Mutating a caller-owned manifest or returned schema cannot mutate registry-owned state.

## Security boundary

The registry is an in-memory metadata catalogue, not a trust or execution boundary. Registering a manifest does not authorize its declared permissions, load code, or execute capabilities. Future execution services must independently enforce caller authorization, approval requirements, sandboxing, resource limits, and audit logging.

## Current limitations

- Entries are lost when the process stops.
- There is no dynamic plugin discovery or installation.
- There is no plugin upgrade/replace operation.
- There are no REST or MCP endpoints yet.
