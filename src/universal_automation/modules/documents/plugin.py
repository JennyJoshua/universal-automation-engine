"""Safe creation of new Markdown, text, and JSON documents in a workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import CapabilityExecutor, HandlerInputError
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.workspace import WorkspaceGuard


class DocumentAutomationModule:
    """Create new documents without overwriting existing workspace files."""

    plugin_id = "uae.document-tools"

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_output_bytes: int = 1_048_576,
    ) -> None:
        if max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")

        self._workspace = WorkspaceGuard(workspace_root)
        self._max_output_bytes = max_output_bytes
        self._manifest = self._build_manifest()
        self._handlers = {
            "create_markdown_document": self._create_markdown_document,
            "create_text_document": self._create_text_document,
            "create_json_document": self._create_json_document,
        }

    @property
    def manifest(self) -> PluginManifest:
        """Return a defensive copy of the document plugin manifest."""
        return self._manifest.model_copy(deep=True)

    def register(self, registry: PluginRegistry, executor: CapabilityExecutor) -> None:
        """Register document capabilities and trusted handlers."""
        if executor.plugin_registry is not registry:
            raise ValueError(
                "Document module and executor must use the same plugin registry instance"
            )

        registry.register(self._manifest)
        for capability_name, handler in self._handlers.items():
            executor.register_handler(self.plugin_id, capability_name, handler)

    def _build_manifest(self) -> PluginManifest:
        output_schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "size_bytes": {"type": "integer", "minimum": 0},
                "created": {"type": "boolean", "const": True},
            },
            "required": ["path", "size_bytes", "created"],
            "additionalProperties": False,
        }

        return PluginManifest(
            plugin_id=self.plugin_id,
            display_name="Workspace Document Tools",
            version="0.1.0",
            description="Create new Markdown, text, and JSON documents in a configured workspace.",
            capabilities=(
                CapabilitySpec(
                    name="create_markdown_document",
                    description="Create a new Markdown document with a title and content.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "minLength": 1},
                            "title": {"type": "string", "minLength": 1, "maxLength": 200},
                            "content": {"type": "string", "maxLength": 1_000_000},
                        },
                        "required": ["path", "title", "content"],
                        "additionalProperties": False,
                    },
                    output_schema=output_schema,
                    permissions=("documents.create",),
                ),
                CapabilitySpec(
                    name="create_text_document",
                    description="Create a new plain-text document.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "minLength": 1},
                            "content": {"type": "string", "maxLength": 1_000_000},
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                    output_schema=output_schema,
                    permissions=("documents.create",),
                ),
                CapabilitySpec(
                    name="create_json_document",
                    description="Create a new formatted JSON document.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "minLength": 1},
                            "data": {},
                        },
                        "required": ["path", "data"],
                        "additionalProperties": False,
                    },
                    output_schema=output_schema,
                    permissions=("documents.create",),
                ),
            ),
        )

    def _create_document(
        self,
        *,
        path: str,
        extension: str,
        content: str,
    ) -> dict[str, Any]:
        if Path(path).suffix.casefold() != extension:
            raise HandlerInputError(f"Document path must use the {extension} extension")

        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HandlerInputError("Document content must be valid UTF-8 text") from exc

        created_path = self._workspace.create_new_file(
            path,
            encoded,
            max_bytes=self._max_output_bytes,
        )
        return {
            "path": self._workspace.relative_path(created_path),
            "size_bytes": len(encoded),
            "created": True,
        }

    def _create_markdown_document(self, data: dict[str, Any]) -> dict[str, Any]:
        title = data["title"].strip()
        if not title:
            raise HandlerInputError("Document title cannot be empty")

        content = f"# {title}\n\n{data['content'].rstrip()}\n"
        return self._create_document(
            path=data["path"],
            extension=".md",
            content=content,
        )

    def _create_text_document(self, data: dict[str, Any]) -> dict[str, Any]:
        return self._create_document(
            path=data["path"],
            extension=".txt",
            content=data["content"],
        )

    def _create_json_document(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            content = json.dumps(
                data["data"],
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ) + "\n"
        except (TypeError, ValueError) as exc:
            raise HandlerInputError("Document data must be valid JSON") from exc

        return self._create_document(
            path=data["path"],
            extension=".json",
            content=content,
        )
