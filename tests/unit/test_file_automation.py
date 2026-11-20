"""Tests for the workspace-confined read-only file automation module."""

import pytest

from universal_automation.core.execution import (
    CapabilityExecutor,
    ExecutionRequest,
    HandlerInputError,
)
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.files import FileAutomationModule
from universal_automation.security import (
    AuthorizationPolicy,
    ExecutionPrincipal,
    InsufficientPermissionsError,
)


def make_engine(workspace, **limits):
    module = FileAutomationModule(workspace, **limits)
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    module.register(registry, executor)
    principal = ExecutionPrincipal(
        subject_id="file-test-user",
        permissions={"files.read"},
    )
    return module, registry, executor, principal


def execute(executor, principal, capability_name, input_data):
    return executor.execute(
        ExecutionRequest(
            request_id=f"file-test-{capability_name}",
            plugin_id=FileAutomationModule.plugin_id,
            capability_name=capability_name,
            input_data=input_data,
        ),
        principal,
    )


def test_module_registers_three_read_only_capabilities(tmp_path) -> None:
    module, registry, executor, _ = make_engine(tmp_path)

    manifest = registry.get(module.plugin_id)

    assert {cap.name for cap in manifest.capabilities} == {
        "list_files",
        "read_text_file",
        "search_text_files",
    }
    assert all(cap.permissions == ("files.read",) for cap in manifest.capabilities)
    assert all(not cap.destructive and not cap.approval_required for cap in manifest.capabilities)
    assert executor.plugin_registry is registry


def test_list_files_returns_sorted_workspace_entries(tmp_path) -> None:
    (tmp_path / "zeta.txt").write_text("z", encoding="utf-8")
    (tmp_path / "alpha.txt").write_text("a", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(executor, principal, "list_files", {"max_results": 10})

    assert [item["name"] for item in result.output_data["files"]] == [
        "alpha.txt",
        "folder",
        "zeta.txt",
    ]
    assert result.output_data["truncated"] is False


def test_list_files_applies_result_and_scan_limits(tmp_path) -> None:
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_directory_entries=10)

    result = execute(executor, principal, "list_files", {"max_results": 2})

    assert len(result.output_data["files"]) == 2
    assert result.output_data["truncated"] is True


def test_list_files_caps_directory_entries_scanned(tmp_path) -> None:
    for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_directory_entries=2)

    result = execute(executor, principal, "list_files", {})

    assert len(result.output_data["files"]) <= 2
    assert result.output_data["truncated"] is True


def test_read_text_file_returns_utf8_content(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("Automation works.", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(executor, principal, "read_text_file", {"path": "notes.txt"})

    assert result.output_data == {
        "path": "notes.txt",
        "content": "Automation works.",
        "size_bytes": len(b"Automation works."),
    }


def test_search_text_files_returns_case_insensitive_matches(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("Hello world\nNo match\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("hello again\n", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(executor, principal, "search_text_files", {"query": "HELLO"})

    assert [(item["path"], item["line_number"]) for item in result.output_data["matches"]] == [
        ("a.txt", 1),
        ("b.md", 1),
    ]
    assert result.output_data["truncated"] is False
    assert result.output_data["files_scanned"] == 2


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "folder/../../outside.txt",
        "/etc/passwd",
        r"C:\Windows\win.ini",
        r"..\outside.txt",
    ],
)
def test_read_rejects_absolute_and_traversal_paths(tmp_path, path: str) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError):
        execute(executor, principal, "read_text_file", {"path": path})


def test_read_rejects_symbolic_link_escape(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = workspace / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this environment")

    _, _, executor, principal = make_engine(workspace)

    with pytest.raises(HandlerInputError, match="Symbolic links"):
        execute(executor, principal, "read_text_file", {"path": "linked.txt"})


def test_list_omits_symbolic_links(tmp_path) -> None:
    (tmp_path / "normal.txt").write_text("safe", encoding="utf-8")
    outside = tmp_path.parent / "outside-file-automation.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        (tmp_path / "linked.txt").symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this environment")
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(executor, principal, "list_files", {})

    assert [item["name"] for item in result.output_data["files"]] == ["normal.txt"]


def test_read_rejects_files_over_configured_size_limit(tmp_path) -> None:
    (tmp_path / "large.txt").write_text("123456", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_file_bytes=5)

    with pytest.raises(HandlerInputError, match="size limit"):
        execute(executor, principal, "read_text_file", {"path": "large.txt"})


def test_read_rejects_non_utf8_binary_files(tmp_path) -> None:
    (tmp_path / "binary.dat").write_bytes(b"\xff\xfe\x00")
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError, match="UTF-8"):
        execute(executor, principal, "read_text_file", {"path": "binary.dat"})


def test_search_skips_binary_files(tmp_path) -> None:
    (tmp_path / "binary.dat").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "text.txt").write_text("needle here", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(executor, principal, "search_text_files", {"query": "needle"})

    assert len(result.output_data["matches"]) == 1
    assert result.output_data["matches"][0]["path"] == "text.txt"


def test_search_respects_file_scan_budget(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("no result", encoding="utf-8")
    (tmp_path / "b.txt").write_text("needle", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_scan_files=1)

    result = execute(executor, principal, "search_text_files", {"query": "needle"})

    assert result.output_data["matches"] == []
    assert result.output_data["files_scanned"] == 1
    assert result.output_data["truncated"] is True


def test_search_respects_total_scan_byte_budget(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("a" * 10, encoding="utf-8")
    (tmp_path / "b.txt").write_text("needle", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_scan_bytes=10)

    result = execute(executor, principal, "search_text_files", {"query": "needle"})

    assert result.output_data["matches"] == []
    assert result.output_data["truncated"] is True


def test_missing_file_returns_safe_input_error(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError, match="not found"):
        execute(executor, principal, "read_text_file", {"path": "missing.txt"})


def test_file_tools_require_files_read_permission(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("private", encoding="utf-8")
    _, _, executor, _ = make_engine(tmp_path)
    unprivileged = ExecutionPrincipal(subject_id="unprivileged-user")

    with pytest.raises(InsufficientPermissionsError):
        execute(executor, unprivileged, "read_text_file", {"path": "notes.txt"})


def test_module_requires_existing_directory(tmp_path) -> None:
    with pytest.raises(ValueError, match="existing directory"):
        FileAutomationModule(tmp_path / "missing")


def test_module_rejects_non_positive_limits(tmp_path) -> None:
    with pytest.raises(ValueError, match="must all be positive"):
        FileAutomationModule(tmp_path, max_scan_files=0)


def test_search_counts_binary_bytes_against_scan_budget(tmp_path) -> None:
    (tmp_path / "a-binary.dat").write_bytes(b"\\xff\\xfe\\x00")
    (tmp_path / "b-text.txt").write_text("needle", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path, max_scan_bytes=3)

    result = execute(executor, principal, "search_text_files", {"query": "needle"})

    assert result.output_data["matches"] == []
    assert result.output_data["files_scanned"] == 2
    assert result.output_data["truncated"] is True
