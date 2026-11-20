"""Illustrative plugin manifest; this file does not execute file operations."""

from universal_automation.core.contracts import CapabilitySpec, PluginManifest

workspace_schema = {
    "type": "object",
    "properties": {"workspace": {"type": "string"}},
    "required": ["workspace"],
    "additionalProperties": False,
}

minimal_file_plugin = PluginManifest(
    plugin_id="example.file-tools",
    display_name="Example File Tools",
    version="1.0.0",
    description="An example manifest for safe, workspace-scoped file capabilities.",
    capabilities=(
        CapabilitySpec(
            name="list_files",
            description="List files in a configured workspace.",
            input_schema=workspace_schema,
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
