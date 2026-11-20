"""Safe creation of Markdown, text, JSON, PDF, DOCX, and XLSX documents."""

from __future__ import annotations

import importlib.util
import json
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

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
        self._available_formats = {
            "pdf": importlib.util.find_spec("reportlab") is not None,
            "docx": importlib.util.find_spec("docx") is not None,
            "xlsx": importlib.util.find_spec("openpyxl") is not None,
        }
        self._manifest = self._build_manifest()
        self._handlers = {
            "create_markdown_document": self._create_markdown_document,
            "create_text_document": self._create_text_document,
            "create_json_document": self._create_json_document,
        }
        if self._available_formats["pdf"]:
            self._handlers["create_pdf_document"] = self._create_pdf_document
        if self._available_formats["docx"]:
            self._handlers["create_docx_document"] = self._create_docx_document
        if self._available_formats["xlsx"]:
            self._handlers["create_xlsx_document"] = self._create_xlsx_document

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
        text_document_input = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "content": {"type": "string", "maxLength": 1_000_000},
            },
            "required": ["path", "title", "content"],
            "additionalProperties": False,
        }
        xlsx_input = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "sheet_name": {"type": "string", "minLength": 1, "maxLength": 31, "default": "Sheet1"},
                "headers": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {"type": "string", "minLength": 1},
                },
                "rows": {
                    "type": "array",
                    "maxItems": 10_000,
                    "items": {
                        "type": "array",
                        "maxItems": 50,
                        "items": {"type": ["string", "number", "boolean", "null"]},
                    },
                },
            },
            "required": ["path", "headers", "rows"],
            "additionalProperties": False,
        }

        capabilities = [
            CapabilitySpec(
                name="create_markdown_document",
                description="Create a new Markdown document with a title and content.",
                input_schema=text_document_input,
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
        ]

        if self._available_formats["pdf"]:
            capabilities.append(
                CapabilitySpec(
                    name="create_pdf_document",
                    description="Create a new PDF document with a title and plain-text content.",
                    input_schema=text_document_input,
                    output_schema=output_schema,
                    permissions=("documents.create",),
                )
            )
        if self._available_formats["docx"]:
            capabilities.append(
                CapabilitySpec(
                    name="create_docx_document",
                    description="Create a new Microsoft Word document with a title and content.",
                    input_schema=text_document_input,
                    output_schema=output_schema,
                    permissions=("documents.create",),
                )
            )
        if self._available_formats["xlsx"]:
            capabilities.append(
                CapabilitySpec(
                    name="create_xlsx_document",
                    description="Create a new Excel workbook from headers and tabular rows.",
                    input_schema=xlsx_input,
                    output_schema=output_schema,
                    permissions=("documents.create",),
                )
            )

        return PluginManifest(
            plugin_id=self.plugin_id,
            display_name="Workspace Document Tools",
            version="0.2.0",
            description="Create new documents in a configured workspace.",
            capabilities=tuple(capabilities),
        )

    def _create_binary_document(
        self,
        *,
        path: str,
        extension: str,
        content: bytes,
    ) -> dict[str, Any]:
        if Path(path).suffix.casefold() != extension:
            raise HandlerInputError(f"Document path must use the {extension} extension")

        created_path = self._workspace.create_new_file(
            path,
            content,
            max_bytes=self._max_output_bytes,
        )
        return {
            "path": self._workspace.relative_path(created_path),
            "size_bytes": len(content),
            "created": True,
        }

    def _create_document(
        self,
        *,
        path: str,
        extension: str,
        content: str,
    ) -> dict[str, Any]:
        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HandlerInputError("Document content must be valid UTF-8 text") from exc

        return self._create_binary_document(
            path=path,
            extension=extension,
            content=encoded,
        )

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

    def _create_pdf_document(self, data: dict[str, Any]) -> dict[str, Any]:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        title = data["title"].strip()
        if not title:
            raise HandlerInputError("Document title cannot be empty")

        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=title,
            author="Universal Automation Engine",
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph(escape(title), styles["Title"]),
            Spacer(1, 12),
        ]
        for paragraph in data["content"].split("\n\n"):
            if paragraph:
                safe_paragraph = escape(paragraph).replace("\n", "<br/>")
                story.append(Paragraph(safe_paragraph, styles["BodyText"]))
                story.append(Spacer(1, 8))

        document.build(story)
        return self._create_binary_document(
            path=data["path"],
            extension=".pdf",
            content=buffer.getvalue(),
        )

    def _create_docx_document(self, data: dict[str, Any]) -> dict[str, Any]:
        from docx import Document

        title = data["title"].strip()
        if not title:
            raise HandlerInputError("Document title cannot be empty")

        document = Document()
        document.add_heading(title, level=1)
        for paragraph in data["content"].split("\n\n"):
            if paragraph:
                document.add_paragraph(paragraph)

        buffer = BytesIO()
        document.save(buffer)
        return self._create_binary_document(
            path=data["path"],
            extension=".docx",
            content=buffer.getvalue(),
        )

    def _create_xlsx_document(self, data: dict[str, Any]) -> dict[str, Any]:
        from openpyxl import Workbook

        sheet_name = data.get("sheet_name", "Sheet1")
        if (
            not sheet_name
            or len(sheet_name) > 31
            or any(character in sheet_name for character in "[]:*?/\\")
            or sheet_name.startswith("'")
            or sheet_name.endswith("'")
        ):
            raise HandlerInputError("Worksheet name is invalid")

        headers = data["headers"]
        rows = data["rows"]
        if not headers or len(headers) > 50:
            raise HandlerInputError("Excel documents require between 1 and 50 columns")
        if len(rows) > 10_000:
            raise HandlerInputError("Excel documents are limited to 10,000 data rows")
        if any(len(row) != len(headers) for row in rows):
            raise HandlerInputError("Every spreadsheet row must match the header column count")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet_name

        for column, value in enumerate(headers, start=1):
            cell = worksheet.cell(row=1, column=column, value=value)
            cell.data_type = "s"

        for row_number, row in enumerate(rows, start=2):
            for column, value in enumerate(row, start=1):
                cell = worksheet.cell(row=row_number, column=column, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"

        buffer = BytesIO()
        workbook.save(buffer)
        return self._create_binary_document(
            path=data["path"],
            extension=".xlsx",
            content=buffer.getvalue(),
        )
