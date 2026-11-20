"""Tests for bounded structured-data automation."""

import json

import pytest

from universal_automation.core.execution import (
    CapabilityExecutor,
    ExecutionRequest,
    HandlerInputError,
)
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.data import StructuredDataModule
from universal_automation.security import (
    AuthorizationPolicy,
    ExecutionPrincipal,
    InsufficientPermissionsError,
)


def make_engine(workspace, **limits):
    module = StructuredDataModule(workspace, **limits)
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    module.register(registry, executor)
    principal = ExecutionPrincipal(
        subject_id="data-test-user",
        permissions={"files.read", "data.create", "data.transform"},
    )
    return module, registry, executor, principal


def execute(executor, principal, capability_name, input_data):
    return executor.execute(
        ExecutionRequest(
            request_id=f"data-test-{capability_name}",
            plugin_id=StructuredDataModule.plugin_id,
            capability_name=capability_name,
            input_data=input_data,
        ),
        principal,
    )


def test_module_registers_expected_capabilities(tmp_path):
    module, registry, executor, _ = make_engine(tmp_path)
    names = {cap.name for cap in registry.get(module.plugin_id).capabilities}
    expected = {"read_csv", "write_csv", "read_json", "write_json", "transform_records"}
    if "read_spreadsheet" in names:
        expected.add("read_spreadsheet")
    assert names == expected
    assert executor.plugin_registry is registry


def test_csv_read_returns_records_and_headers(tmp_path):
    (tmp_path / "people.csv").write_text("name,age\nAri,12\nBela,13\n", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)
    result = execute(executor, principal, "read_csv", {"path": "people.csv"})
    assert result.output_data == {
        "headers": ["name", "age"],
        "records": [{"name": "Ari", "age": "12"}, {"name": "Bela", "age": "13"}],
        "row_count": 2,
        "truncated": False,
    }


def test_csv_read_enforces_row_limit(tmp_path):
    (tmp_path / "people.csv").write_text("name\nA\nB\nC\n", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_rows=2)
    result = execute(executor, principal, "read_csv", {"path": "people.csv"})
    assert result.output_data["records"] == [{"name": "A"}, {"name": "B"}]
    assert result.output_data["truncated"] is True


@pytest.mark.parametrize(
    "csv_text",
    ["name,name\nA,B\n", "name,age\nA\n", "name\nA,B\n", ",age\nA,1\n"],
)
def test_csv_read_rejects_malformed_headers_or_rows(tmp_path, csv_text):
    (tmp_path / "invalid.csv").write_text(csv_text, encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)
    with pytest.raises(HandlerInputError):
        execute(executor, principal, "read_csv", {"path": "invalid.csv"})


def test_csv_read_rejects_wrong_extension_and_oversized_files(tmp_path):
    (tmp_path / "data.txt").write_text("name\nA\n", encoding="utf-8")
    (tmp_path / "large.csv").write_text("x" * 30, encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_file_bytes=20)
    with pytest.raises(HandlerInputError, match="extension"):
        execute(executor, principal, "read_csv", {"path": "data.txt"})
    with pytest.raises(HandlerInputError, match="size limit"):
        execute(executor, principal, "read_csv", {"path": "large.csv"})


def test_csv_write_neutralizes_formula_injection_and_creates_new_file(tmp_path):
    _, _, executor, principal = make_engine(tmp_path)
    result = execute(
        executor,
        principal,
        "write_csv",
        {
            "path": "export.csv",
            "headers": ["name", "formula", "amount"],
            "rows": [["Ari", "=1+1", -3]],
        },
    )
    assert (tmp_path / "export.csv").read_text(encoding="utf-8") == (
        "name,formula,amount\nAri,'=1+1,-3\n"
    )
    assert result.output_data["created"] is True
    assert result.output_data["row_count"] == 1


def test_csv_write_rejects_mismatched_rows_and_existing_files(tmp_path):
    (tmp_path / "existing.csv").write_text("safe", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)
    with pytest.raises(HandlerInputError, match="header column count"):
        execute(
            executor,
            principal,
            "write_csv",
            {"path": "new.csv", "headers": ["a", "b"], "rows": [[1]]},
        )
    with pytest.raises(HandlerInputError, match="already exists"):
        execute(
            executor,
            principal,
            "write_csv",
            {"path": "existing.csv", "headers": ["a"], "rows": [[1]]},
        )


def test_json_read_and_write_round_trip(tmp_path):
    source = {"school": "Baimuru", "students": [{"name": "Ari", "age": 12}]}
    (tmp_path / "source.json").write_text(json.dumps(source), encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)
    read = execute(executor, principal, "read_json", {"path": "source.json"})
    written = execute(
        executor,
        principal,
        "write_json",
        {"path": "copy.json", "data": read.output_data["data"]},
    )
    assert json.loads((tmp_path / "copy.json").read_text(encoding="utf-8")) == source
    assert written.output_data["created"] is True


def test_json_read_rejects_invalid_json_and_traversal(tmp_path):
    (tmp_path / "invalid.json").write_text("{bad", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)
    with pytest.raises(HandlerInputError, match="invalid"):
        execute(executor, principal, "read_json", {"path": "invalid.json"})
    with pytest.raises(HandlerInputError, match="traversal"):
        execute(executor, principal, "read_json", {"path": "../outside.json"})


def test_transform_records_filters_sorts_projects_and_limits(tmp_path):
    _, _, executor, principal = make_engine(tmp_path)
    result = execute(
        executor,
        principal,
        "transform_records",
        {
            "records": [
                {"name": "Ari", "age": 12, "class": "A"},
                {"name": "Bela", "age": 10, "class": "A"},
                {"name": "Cato", "age": 11, "class": "B"},
            ],
            "filters": {"class": "A"},
            "sort_by": "age",
            "columns": ["name", "age"],
            "limit": 1,
        },
    )
    assert result.output_data == {"records": [{"name": "Bela", "age": 10}], "row_count": 1}


def test_transform_records_rejects_non_object_records_and_incompatible_sort(tmp_path):
    _, _, executor, principal = make_engine(tmp_path)
    with pytest.raises(HandlerInputError, match="JSON object"):
        execute(executor, principal, "transform_records", {"records": [{"a": 1}, "bad"]})
    with pytest.raises(HandlerInputError, match="compatible types"):
        execute(
            executor,
            principal,
            "transform_records",
            {"records": [{"v": 1}, {"v": "two"}], "sort_by": "v"},
        )


def test_data_operations_require_permissions(tmp_path):
    (tmp_path / "data.json").write_text("{}", encoding="utf-8")
    _, _, executor, _ = make_engine(tmp_path)
    unprivileged = ExecutionPrincipal(subject_id="no-data-permissions")
    with pytest.raises(InsufficientPermissionsError):
        execute(executor, unprivileged, "read_json", {"path": "data.json"})


def test_csv_output_size_limit_is_enforced(tmp_path):
    _, _, executor, principal = make_engine(tmp_path, max_output_bytes=5)
    with pytest.raises(HandlerInputError, match="output-size limit"):
        execute(
            executor,
            principal,
            "write_csv",
            {"path": "large.csv", "headers": ["value"], "rows": [["a much longer value"]]},
        )


def test_spreadsheet_read_extracts_bounded_rows_when_available(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["name", "score"])
    sheet.append(["Ari", 10])
    sheet.append(["Bela", 11])
    workbook.save(tmp_path / "scores.xlsx")
    _, registry, executor, principal = make_engine(tmp_path, max_rows=1)
    if not registry.has_capability(StructuredDataModule.plugin_id, "read_spreadsheet"):
        pytest.skip("openpyxl is unavailable")
    result = execute(executor, principal, "read_spreadsheet", {"path": "scores.xlsx"})
    assert result.output_data["headers"] == ["name", "score"]
    assert result.output_data["records"] == [{"name": "Ari", "score": 10}]
    assert result.output_data["truncated"] is True
