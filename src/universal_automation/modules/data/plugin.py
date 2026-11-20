"""Bounded CSV, JSON, and optional XLSX data automation."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import CapabilityExecutor, HandlerInputError
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.workspace import WorkspaceGuard


class StructuredDataModule:
    """Read, transform, and create bounded structured-data files in one workspace."""

    plugin_id = "uae.structured-data"

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_file_bytes: int = 2_097_152,
        max_output_bytes: int = 2_097_152,
        max_rows: int = 10_000,
        max_columns: int = 50,
    ) -> None:
        if min(max_file_bytes, max_output_bytes, max_rows, max_columns) < 1:
            raise ValueError("Structured-data limits must all be positive")
        if max_columns > 200 or max_rows > 100_000:
            raise ValueError("Structured-data limits exceed the supported hard maximum")

        self._workspace = WorkspaceGuard(workspace_root)
        self._max_file_bytes = max_file_bytes
        self._max_output_bytes = max_output_bytes
        self._max_rows = max_rows
        self._max_columns = max_columns
        self._xlsx_available = importlib.util.find_spec("openpyxl") is not None
        self._manifest = self._build_manifest()
        self._handlers = {
            "read_csv": self._read_csv,
            "write_csv": self._write_csv,
            "read_json": self._read_json,
            "write_json": self._write_json,
            "transform_records": self._transform_records,
        }
        if self._xlsx_available:
            self._handlers["read_spreadsheet"] = self._read_spreadsheet

    @property
    def manifest(self) -> PluginManifest:
        """Return a defensive copy of the module manifest."""
        return self._manifest.model_copy(deep=True)

    def register(self, registry: PluginRegistry, executor: CapabilityExecutor) -> None:
        """Register this module with the shared engine."""
        if executor.plugin_registry is not registry:
            raise ValueError("Data module and executor must use the same plugin registry")
        registry.register(self._manifest)
        for name, handler in self._handlers.items():
            executor.register_handler(self.plugin_id, name, handler)

    def _build_manifest(self) -> PluginManifest:
        file_input = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 500},
                "max_rows": {"type": "integer", "minimum": 1, "maximum": self._max_rows},
            },
            "required": ["path"],
            "additionalProperties": False,
        }
        output_schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "size_bytes": {"type": "integer", "minimum": 0},
                "row_count": {"type": "integer", "minimum": 0},
                "created": {"type": "boolean", "const": True},
            },
            "required": ["path", "size_bytes", "row_count", "created"],
            "additionalProperties": False,
        }
        csv_write_input = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 500},
                "headers": {
                    "type": "array", "minItems": 1, "maxItems": self._max_columns,
                    "items": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "rows": {
                    "type": "array", "maxItems": self._max_rows,
                    "items": {
                        "type": "array", "maxItems": self._max_columns,
                        "items": {"type": ["string", "number", "integer", "boolean", "null"]},
                    },
                },
            },
            "required": ["path", "headers", "rows"],
            "additionalProperties": False,
        }
        json_write_input = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 500},
                "data": {},
            },
            "required": ["path", "data"],
            "additionalProperties": False,
        }
        transform_input = {
            "type": "object",
            "properties": {
                "records": {
                    "type": "array", "maxItems": self._max_rows,
                    "items": {"type": "object"},
                },
                "filters": {"type": "object"},
                "columns": {
                    "type": "array", "maxItems": self._max_columns,
                    "items": {"type": "string", "minLength": 1},
                },
                "sort_by": {"type": "string", "maxLength": 200},
                "descending": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "minimum": 1, "maximum": self._max_rows},
            },
            "required": ["records"],
            "additionalProperties": False,
        }
        transform_output = {
            "type": "object",
            "properties": {
                "records": {"type": "array", "items": {"type": "object"}},
                "row_count": {"type": "integer", "minimum": 0},
            },
            "required": ["records", "row_count"],
            "additionalProperties": False,
        }
        capabilities = [
            CapabilitySpec(
                name="read_csv",
                description="Read a bounded CSV file as records with validated headers.",
                input_schema=file_input,
                output_schema={
                    "type": "object",
                    "properties": {
                        "headers": {"type": "array", "items": {"type": "string"}},
                        "records": {"type": "array", "items": {"type": "object"}},
                        "row_count": {"type": "integer", "minimum": 0},
                        "truncated": {"type": "boolean"},
                    },
                    "required": ["headers", "records", "row_count", "truncated"],
                    "additionalProperties": False,
                },
                permissions=("files.read",),
            ),
            CapabilitySpec(
                name="write_csv",
                description="Create a new bounded CSV file; spreadsheet formulas are neutralized.",
                input_schema=csv_write_input,
                output_schema=output_schema,
                permissions=("data.create",),
            ),
            CapabilitySpec(
                name="read_json",
                description="Parse a bounded JSON file and return its data value.",
                input_schema=file_input,
                output_schema={
                    "type": "object",
                    "properties": {"data": {}},
                    "required": ["data"],
                    "additionalProperties": False,
                },
                permissions=("files.read",),
            ),
            CapabilitySpec(
                name="write_json",
                description="Serialize JSON data into a new workspace file.",
                input_schema=json_write_input,
                output_schema=output_schema,
                permissions=("data.create",),
            ),
            CapabilitySpec(
                name="transform_records",
                description="Filter, sort, project, and limit a bounded list of JSON records.",
                input_schema=transform_input,
                output_schema=transform_output,
                permissions=("data.transform",),
            ),
        ]
        if self._xlsx_available:
            capabilities.append(
                CapabilitySpec(
                    name="read_spreadsheet",
                    description="Read a bounded XLSX worksheet as records.",
                    input_schema={
                        **file_input,
                        "properties": {
                            **file_input["properties"],
                            "sheet_name": {"type": "string", "minLength": 1, "maxLength": 31},
                        },
                    },
                    output_schema={
                        "type": "object",
                        "properties": {
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "records": {"type": "array", "items": {"type": "object"}},
                            "row_count": {"type": "integer", "minimum": 0},
                            "truncated": {"type": "boolean"},
                        },
                        "required": ["headers", "records", "row_count", "truncated"],
                        "additionalProperties": False,
                    },
                    permissions=("files.read",),
                )
            )
        return PluginManifest(
            plugin_id=self.plugin_id,
            display_name="Structured Data Tools",
            version="0.1.0",
            description="Bounded CSV, JSON, and optional XLSX data operations in a configured workspace.",
            capabilities=tuple(capabilities),
        )

    def _read_bytes(self, path: str, extension: str) -> bytes:
        if Path(path).suffix.casefold() != extension:
            raise HandlerInputError(f"Input path must use the {extension} extension")
        return self._workspace.read_bytes(path, max_bytes=self._max_file_bytes)

    def _validate_payload_size(self, value: Any) -> None:
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise HandlerInputError("Input must contain valid JSON-compatible values") from exc
        if len(encoded) > self._max_file_bytes:
            raise HandlerInputError("Structured-data input exceeds the configured size limit")

    def _create_file(self, path: str, extension: str, content: bytes, row_count: int) -> dict[str, Any]:
        if Path(path).suffix.casefold() != extension:
            raise HandlerInputError(f"Output path must use the {extension} extension")
        created = self._workspace.create_new_file(path, content, max_bytes=self._max_output_bytes)
        return {
            "path": self._workspace.relative_path(created),
            "size_bytes": len(content),
            "row_count": row_count,
            "created": True,
        }

    def _read_csv(self, data: dict[str, Any]) -> dict[str, Any]:
        raw = self._read_bytes(data["path"], ".csv")
        try:
            text = raw.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            headers = reader.fieldnames
            if not headers or len(headers) > self._max_columns:
                raise HandlerInputError("CSV must contain between 1 and the configured maximum columns")
            if any(not header or not header.strip() for header in headers):
                raise HandlerInputError("CSV headers cannot be empty")
            if len(headers) != len(set(headers)):
                raise HandlerInputError("CSV headers must be unique")
            records = []
            limit = min(data.get("max_rows", self._max_rows), self._max_rows)
            for row in reader:
                if None in row:
                    raise HandlerInputError("CSV row contains more values than its header")
                if any(value is None for value in row.values()):
                    raise HandlerInputError("CSV row contains fewer values than its header")
                if len(records) >= limit:
                    return {"headers": headers, "records": records, "row_count": len(records), "truncated": True}
                records.append(row)
        except (UnicodeDecodeError, csv.Error) as exc:
            raise HandlerInputError("CSV file is invalid or is not UTF-8 text") from exc
        return {"headers": headers, "records": records, "row_count": len(records), "truncated": False}

    @staticmethod
    def _safe_csv_cell(value: Any) -> str | int | float | bool:
        if value is None:
            return ""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
        if not isinstance(value, str):
            raise HandlerInputError("CSV cells must be strings, numbers, booleans, or null")
        if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    def _write_csv(self, data: dict[str, Any]) -> dict[str, Any]:
        self._validate_payload_size(data)
        headers, rows = data["headers"], data["rows"]
        if len(headers) != len(set(headers)):
            raise HandlerInputError("CSV headers must be unique")
        if any(len(row) != len(headers) for row in rows):
            raise HandlerInputError("Every CSV row must match the header column count")
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(headers)
        for row in rows:
            writer.writerow([self._safe_csv_cell(value) for value in row])
        try:
            encoded = buffer.getvalue().encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HandlerInputError("CSV content must be valid UTF-8 text") from exc
        return self._create_file(data["path"], ".csv", encoded, len(rows))

    def _read_json(self, data: dict[str, Any]) -> dict[str, Any]:
        raw = self._read_bytes(data["path"], ".json")
        try:
            parsed = json.loads(raw.decode("utf-8"))
            json.dumps(parsed, allow_nan=False)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise HandlerInputError("JSON file is invalid or contains unsupported values") from exc
        return {"data": parsed}

    def _write_json(self, data: dict[str, Any]) -> dict[str, Any]:
        self._validate_payload_size(data["data"])
        try:
            encoded = (json.dumps(data["data"], ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise HandlerInputError("Data must be valid JSON") from exc
        return self._create_file(data["path"], ".json", encoded, 0)

    def _transform_records(self, data: dict[str, Any]) -> dict[str, Any]:
        self._validate_payload_size(data["records"])
        records = data["records"]
        filters = data.get("filters", {})
        if not all(isinstance(record, dict) for record in records):
            raise HandlerInputError("Every record must be a JSON object")
        if not isinstance(filters, dict):
            raise HandlerInputError("Filters must be an object")
        selected = [record for record in records if all(record.get(key) == value for key, value in filters.items())]
        sort_by = data.get("sort_by")
        if sort_by:
            try:
                selected.sort(key=lambda record: (record.get(sort_by) is None, record.get(sort_by)), reverse=data.get("descending", False))
            except TypeError as exc:
                raise HandlerInputError("Selected sort values must have compatible types") from exc
        columns = data.get("columns")
        if columns is not None:
            selected = [{key: record[key] for key in columns if key in record} for record in selected]
        selected = selected[: data.get("limit", self._max_rows)]
        return {"records": selected, "row_count": len(selected)}

    def _read_spreadsheet(self, data: dict[str, Any]) -> dict[str, Any]:
        from io import BytesIO
        from openpyxl import load_workbook

        raw = self._read_bytes(data["path"], ".xlsx")
        try:
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > 1_000 or sum(item.file_size for item in entries) > self._max_file_bytes * 20:
                    raise HandlerInputError("Spreadsheet expands beyond the configured safety limit")
            workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
            sheet_name = data.get("sheet_name")
            if sheet_name is not None and sheet_name not in workbook.sheetnames:
                raise HandlerInputError("Worksheet was not found")
            sheet = workbook[sheet_name] if sheet_name else workbook.active
            row_limit = min(data.get("max_rows", self._max_rows), self._max_rows)
            if sheet.max_column > self._max_columns:
                raise HandlerInputError("Worksheet exceeds the configured column limit")
            iterator = sheet.iter_rows(
                values_only=True,
                max_col=sheet.max_column,
                max_row=min(sheet.max_row or row_limit + 2, row_limit + 2),
            )
            first_row = next(iterator, None)
            if not first_row:
                raise HandlerInputError("Worksheet must contain a header row within the column limit")
            headers = [str(value).strip() if value is not None else "" for value in first_row]
            if any(not value for value in headers) or len(headers) != len(set(headers)):
                raise HandlerInputError("Worksheet headers must be non-empty and unique")
            records = []
            for row in iterator:
                if len(records) >= row_limit:
                    return {"headers": headers, "records": records, "row_count": len(records), "truncated": True}
                values = list(row[: len(headers)])
                values.extend([None] * (len(headers) - len(values)))
                records.append(dict(zip(headers, values, strict=True)))
            return {"headers": headers, "records": records, "row_count": len(records), "truncated": False}
        except HandlerInputError:
            raise
        except Exception as exc:
            raise HandlerInputError("Spreadsheet file is invalid or could not be read") from exc
        finally:
            if "workbook" in locals():
                workbook.close()
