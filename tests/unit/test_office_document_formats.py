"""Tests for optional PDF, DOCX, and XLSX document generation."""

import pytest
from docx import Document
from openpyxl import load_workbook

from universal_automation.core.execution import (
    CapabilityExecutor,
    ExecutionRequest,
    HandlerInputError,
)
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.documents import DocumentAutomationModule
from universal_automation.security import AuthorizationPolicy, ExecutionPrincipal


def make_engine(workspace, *, max_output_bytes=1_048_576):
    module = DocumentAutomationModule(workspace, max_output_bytes=max_output_bytes)
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    module.register(registry, executor)
    principal = ExecutionPrincipal(
        subject_id="office-document-user",
        permissions={"documents.create"},
    )
    return module, registry, executor, principal


def execute(executor, principal, capability_name, input_data):
    return executor.execute(
        ExecutionRequest(
            request_id=f"office-test-{capability_name}",
            plugin_id=DocumentAutomationModule.plugin_id,
            capability_name=capability_name,
            input_data=input_data,
        ),
        principal,
    )


def test_optional_office_capabilities_are_registered_when_dependencies_exist(tmp_path) -> None:
    module, registry, _, _ = make_engine(tmp_path)

    names = {cap.name for cap in registry.get(module.plugin_id).capabilities}

    assert "create_pdf_document" in names
    assert "create_docx_document" in names
    assert "create_xlsx_document" in names


def test_optional_capabilities_are_omitted_when_dependencies_are_missing(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "universal_automation.modules.documents.plugin.importlib.util.find_spec",
        lambda _name: None,
    )
    module = DocumentAutomationModule(tmp_path)

    names = {cap.name for cap in module.manifest.capabilities}

    assert names == {
        "create_markdown_document",
        "create_text_document",
        "create_json_document",
    }


def test_create_pdf_document_generates_valid_pdf_file(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(
        executor,
        principal,
        "create_pdf_document",
        {
            "path": "report.pdf",
            "title": "PDF Report",
            "content": "First paragraph.\n\nText with <markup> & symbols.",
        },
    )

    pdf_bytes = (tmp_path / "report.pdf").read_bytes()
    assert pdf_bytes.startswith(b"%PDF-")
    assert result.output_data["created"] is True
    assert result.output_data["size_bytes"] == len(pdf_bytes)


def test_create_docx_document_generates_readable_word_file(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(
        executor,
        principal,
        "create_docx_document",
        {
            "path": "report.docx",
            "title": "Word Report",
            "content": "First paragraph.\n\nSecond paragraph with <markup> & symbols.",
        },
    )

    document = Document(tmp_path / "report.docx")
    assert document.paragraphs[0].text == "Word Report"
    assert document.paragraphs[1].text == "First paragraph."
    assert document.paragraphs[2].text == "Second paragraph with <markup> & symbols."
    assert result.output_data["created"] is True


def test_create_xlsx_document_preserves_text_and_numeric_cells(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(
        executor,
        principal,
        "create_xlsx_document",
        {
            "path": "report.xlsx",
            "sheet_name": "Summary",
            "headers": ["Name", "Formula-like value", "Count"],
            "rows": [
                ["Item A", "=1+1", 3],
                ["Item B", "+SUM(A1:A2)", 4],
            ],
        },
    )

    workbook = load_workbook(tmp_path / "report.xlsx", data_only=False)
    worksheet = workbook["Summary"]

    assert worksheet["A2"].value == "Item A"
    assert worksheet["B2"].value == "=1+1"
    assert worksheet["B2"].data_type == "s"
    assert worksheet["C2"].value == 3
    assert worksheet["C2"].data_type == "n"
    assert result.output_data["created"] is True


def test_xlsx_rejects_invalid_worksheet_names(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError, match="Worksheet name is invalid"):
        execute(
            executor,
            principal,
            "create_xlsx_document",
            {
                "path": "invalid.xlsx",
                "sheet_name": "Bad/Name",
                "headers": ["Name"],
                "rows": [],
            },
        )


def test_xlsx_requires_each_row_to_match_header_count(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError, match="header column count"):
        execute(
            executor,
            principal,
            "create_xlsx_document",
            {
                "path": "invalid.xlsx",
                "headers": ["Name", "Count"],
                "rows": [["Only one cell"]],
            },
        )


def test_optional_office_formats_obey_output_size_limit(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path, max_output_bytes=10)

    with pytest.raises(HandlerInputError, match="output-size limit"):
        execute(
            executor,
            principal,
            "create_docx_document",
            {
                "path": "too-large.docx",
                "title": "Large",
                "content": "This will generate more than ten bytes.",
            },
        )
