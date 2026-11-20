# Automation Plugin Contract

## Status

Contract version: **1.0** (initial development contract).

This contract defines the metadata and capability declarations required for an automation module to be understood by the Universal Automation Engine. It is transport-independent: REST and MCP adapters will consume the same manifest and capability definitions.

## Plugin identity

Every plugin declares:

- `plugin_id`: stable lowercase identifier. Letters and digits are separated, where needed, by dots, underscores, or hyphens.
- `display_name`: human-readable name.
- `version`: semantic version in `MAJOR.MINOR.PATCH` form, optionally including prerelease or build metadata.
- `contract_version`: version of this manifest contract. The initial supported value is `1.0`.
- `description`: concise purpose statement.
- `capabilities`: one or more uniquely named actions.

## Capability declaration

Each capability declares:

- `name`: lowercase identifier using letters, digits, and underscores.
- `description`: what the action does.
- `input_schema`: JSON Schema object describing accepted input.
- `output_schema`: JSON Schema object describing its result.
- `permissions`: explicit permission identifiers required by the action.
- `destructive`: whether the action can delete, overwrite, or otherwise cause consequential changes.
- `approval_required`: whether an explicit approval is required before execution.

Destructive capabilities must set `approval_required: true`. A capability with no external side effects may declare an empty permissions list.

## JSON Schema rules

Input and output schemas must be valid JSON Schema documents with an object at the root. Schema validation checks the schema definition itself; validating actual runtime payloads against those schemas is a separate execution-layer responsibility.

The engine does not fetch remote references while validating a schema. Plugin authors should prefer self-contained schemas. Runtime payload validation and reference-resolution policy will be specified before the execution engine is introduced.

## Example

```python
from universal_automation.core.contracts import CapabilitySpec, PluginManifest

file_schema = {
    "type": "object",
    "properties": {"workspace": {"type": "string"}},
    "required": ["workspace"],
    "additionalProperties": False,
}

manifest = PluginManifest(
    plugin_id="example.file-tools",
    display_name="Example File Tools",
    version="1.0.0",
    description="Safe file operations for an explicitly configured workspace.",
    capabilities=(
        CapabilitySpec(
            name="list_files",
            description="List files in the configured workspace.",
            input_schema=file_schema,
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
```

## Validation and compatibility

The Python package exposes `CapabilitySpec` and `PluginManifest` as typed Pydantic models. Invalid identifiers, malformed semantic versions, invalid JSON Schemas, duplicate capability names, duplicate permissions, and unsafe destructive-action declarations are rejected.

The initial contract is intentionally small. Future contract changes must be versioned and documented. New optional fields may be added compatibly; changing the meaning or structure of existing required fields requires a new contract version and a migration plan.

## Security boundary

A manifest is descriptive metadata, not proof that a plugin is safe. Registration and execution layers must independently enforce authentication, authorization, approval, isolation, resource limits, and audit logging. A plugin must never be able to grant itself permissions merely by declaring them.
