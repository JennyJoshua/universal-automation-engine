"""Tests for safe workspace document creation."""

import json

import pytest

from universal_automation.core.execution import (
    CapabilityExecutor,
    ExecutionRequest,
    HandlerInputError,
    InputValidationError,
)
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.documents import DocumentAutomationModule
from universal_automation.security import (
    AuthorizationPolicy,
    ExecutionPrincipal,
    InsufficientPermissionsError,
)


def make_engine(workspace, *, max_output_bytes=1_048_576):
    module = DocumentAutomationModule(
        workspace,
        max_output_bytes=max_output_bytes,
    )
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    module.register(registry, executor)
    principal = ExecutionPrincipal(
        subject_id="document-test-user",
        permissions={"documents.create"},
    )
    return module, registry, executor, principal


def execute(executor, principal, capability_name, input_data):
    return executor.execute(
        ExecutionRequest(
            request_id=f"document-test-{capability_name}",
            plugin_id=DocumentAutomationModule.plugin_id,
            capability_name=capability_name,
            input_data=input_data,
        ),
        principal,
    )


def test_module_registers_three_document_creation_capabilities(tmp_path) -> None:
    module, registry, executor, _ = make_engine(tmp_path)

    manifest = registry.get(module.plugin_id)

    assert {cap.name for cap in manifest.capabilities} == {
        "create_markdown_document",
        "create_text_document",
        "create_json_document",
    }
    assert all(cap.permissions == ("documents.create",) for cap in manifest.capabilities)
    assert all(not cap.destructive and not cap.approval_required for cap in manifest.capabilities)
    assert executor.plugin_registry is registry


def test_create_markdown_document_writes_expected_content(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    (tmp_path / "reports").mkdir()
    result = execute(
        executor,
        principal,
        "create_markdown_document",
        {
            "path": "reports/summary.md",
            "title": "Monthly Summary",
            "content": "Revenue increased.",
        },
    )
    assert result.output_data["path"] == "reports/summary.md"
    assert result.output_data["created"] is True
    assert (tmp_path / "reports" / "summary.md").read_text(encoding="utf-8") == (
        "# Monthly Summary\n\nRevenue increased.\n"
    )


def test_create_text_document_writes_utf8_content(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    result = execute(
        executor,
        principal,
        "create_text_document",
        {"path": "notes.txt", "content": "Hello Papua New Guinea."},
    )

    assert result.output_data["size_bytes"] == len(b"Hello Papua New Guinea.")
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "Hello Papua New Guinea."


def test_create_json_document_writes_valid_formatted_json(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    (tmp_path / "data").mkdir()
    result = execute(
        executor,
        principal,
        "create_json_document",
        {
            "path": "data/result.json",
            "data": {"status": "ready", "count": 3},
        },
    )
    assert result.output_data["path"] == "data/result.json"
    assert json.loads((tmp_path / "data" / "result.json").read_text(encoding="utf-8")) == {
        "status": "ready",
        "count": 3,
    }


def test_document_creation_never_overwrites_existing_files(tmp_path) -> None:
    existing = tmp_path / "existing.txt"
    existing.write_text("original", encoding="utf-8")
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError, match="overwriting is not supported"):
        execute(
            executor,
            principal,
            "create_text_document",
            {"path": "existing.txt", "content": "replacement"},
        )

    assert existing.read_text(encoding="utf-8") == "original"


@pytest.mark.parametrize(
    ("capability", "input_data"),
    [
        (
            "create_text_document",
            {"path": "../outside.txt", "content": "blocked"},
        ),
        (
            "create_text_document",
            {"path": "/tmp/outside.txt", "content": "blocked"},
        ),
        (
            "create_markdown_document",
            {"path": "wrong.txt", "title": "Title", "content": "Body"},
        ),
        (
            "create_json_document",
            {"path": "wrong.md", "data": {"key": "value"}},
        ),
    ],
)
def test_document_creation_rejects_unsafe_paths_and_extensions(
    tmp_path,
    capability: str,
    input_data: dict[str, object],
) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError):
        execute(executor, principal, capability, input_data)


def test_document_creation_rejects_symlink_parent(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (workspace / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this environment")
    _, _, executor, principal = make_engine(workspace)

    with pytest.raises(HandlerInputError, match="Symbolic links"):
        execute(
            executor,
            principal,
            "create_text_document",
            {"path": "linked/new.txt", "content": "blocked"},
        )


def test_document_creation_requires_existing_parent_directory(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError, match="Parent directory"):
        execute(
            executor,
            principal,
            "create_text_document",
            {"path": "missing/new.txt", "content": "blocked"},
        )


def test_document_creation_enforces_output_size_limit(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path, max_output_bytes=5)

    with pytest.raises(HandlerInputError, match="output-size limit"):
        execute(
            executor,
            principal,
            "create_text_document",
            {"path": "large.txt", "content": "more than five bytes"},
        )


def test_markdown_title_cannot_be_blank(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(HandlerInputError, match="title cannot be empty"):
        execute(
            executor,
            principal,
            "create_markdown_document",
            {"path": "blank.md", "title": "   ", "content": "Body"},
        )


def test_document_tools_require_documents_create_permission(tmp_path) -> None:
    _, _, executor, _ = make_engine(tmp_path)
    unprivileged = ExecutionPrincipal(subject_id="unprivileged-user")

    with pytest.raises(InsufficientPermissionsError):
        execute(
            executor,
            unprivileged,
            "create_text_document",
            {"path": "blocked.txt", "content": "blocked"},
        )


def test_json_document_rejects_non_finite_numbers(tmp_path) -> None:
    _, _, executor, principal = make_engine(tmp_path)

    with pytest.raises(InputValidationError):
        execute(
            executor,
            principal,
            "create_json_document",
            {"path": "invalid.json", "data": {"value": float("nan")}},
        )
