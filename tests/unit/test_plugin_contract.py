"""Tests for the versioned automation plugin contract."""

import pytest
from pydantic import ValidationError

from universal_automation.core.contracts import CapabilitySpec, PluginManifest

OBJECT_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
    "additionalProperties": False,
}


def make_capability(**overrides: object) -> CapabilitySpec:
    values: dict[str, object] = {
        "name": "organize_files",
        "description": "Organize files in an approved workspace.",
        "input_schema": OBJECT_SCHEMA,
        "output_schema": {
            "type": "object",
            "properties": {"organized_count": {"type": "integer", "minimum": 0}},
            "required": ["organized_count"],
            "additionalProperties": False,
        },
        "permissions": ("files.read", "files.write"),
    }
    values.update(overrides)
    return CapabilitySpec.model_validate(values)


def make_manifest(**overrides: object) -> PluginManifest:
    values: dict[str, object] = {
        "plugin_id": "uae.file-tools",
        "display_name": "File Tools",
        "version": "1.2.3",
        "description": "File management automation capabilities.",
        "capabilities": (make_capability(),),
    }
    values.update(overrides)
    return PluginManifest.model_validate(values)


def test_valid_manifest_is_accepted() -> None:
    manifest = make_manifest()

    assert manifest.plugin_id == "uae.file-tools"
    assert manifest.contract_version == "1.0"
    assert manifest.capabilities[0].name == "organize_files"


@pytest.mark.parametrize("version", ["1", "1.2", "v1.2.3", "01.2.3", "1.2.3-", "1.2.3-01"])
def test_invalid_semantic_versions_are_rejected(version: str) -> None:
    with pytest.raises(ValidationError, match="semantic versioning"):
        make_manifest(version=version)


@pytest.mark.parametrize("plugin_id", ["UpperCase", "-starts-with-dash", "has spaces", ""])
def test_invalid_plugin_ids_are_rejected(plugin_id: str) -> None:
    with pytest.raises(ValidationError):
        make_manifest(plugin_id=plugin_id)


def test_duplicate_capability_names_are_rejected() -> None:
    capability = make_capability()
    with pytest.raises(ValidationError, match="unique"):
        make_manifest(capabilities=(capability, capability))


def test_invalid_json_schema_is_rejected() -> None:
    with pytest.raises(ValidationError, match="valid JSON Schema"):
        make_capability(input_schema={"type": "object", "properties": {"x": {"type": "unknown"}}})


def test_non_object_root_schema_is_rejected() -> None:
    with pytest.raises(ValidationError, match="type='object'"):
        make_capability(input_schema={"type": "string"})


def test_duplicate_permissions_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        make_capability(permissions=("files.read", "files.read"))


def test_invalid_permission_identifier_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Invalid permission"):
        make_capability(permissions=("Files Read",))


def test_destructive_capability_requires_approval() -> None:
    with pytest.raises(ValidationError, match="explicit approval"):
        make_capability(destructive=True)


def test_destructive_capability_with_approval_is_accepted() -> None:
    capability = make_capability(destructive=True, approval_required=True)

    assert capability.destructive is True
    assert capability.approval_required is True


def test_model_fields_cannot_be_reassigned() -> None:
    manifest = make_manifest()

    with pytest.raises(ValidationError):
        manifest.version = "2.0.0"  # type: ignore[misc]


def test_semantic_prerelease_and_build_versions_are_accepted() -> None:
    manifest = make_manifest(version="2.1.0-rc.1+build.7")

    assert manifest.version == "2.1.0-rc.1+build.7"


def test_remote_json_schema_references_are_rejected() -> None:
    with pytest.raises(ValidationError, match="remote schema reference"):
        make_capability(
            input_schema={
                "type": "object",
                "properties": {"external": {"$ref": "https://example.com/schema.json"}},
            }
        )
