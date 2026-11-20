"""Tests for plugin registration and capability discovery."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.registry import (
    CapabilityNotFoundError,
    PluginAlreadyRegisteredError,
    PluginNotFoundError,
    PluginRegistry,
)

def make_manifest(
    plugin_id: str = "example.file-tools",
    version: str = "1.0.0",
    capability_name: str = "list_files",
) -> PluginManifest:
    return PluginManifest(
        plugin_id=plugin_id,
        display_name="Example File Tools",
        version=version,
        description="Example file capabilities.",
        capabilities=(
            CapabilitySpec(
                name=capability_name,
                description="List files in an approved workspace.",
                input_schema={
                    "type": "object",
                    "properties": {"workspace": {"type": "string"}},
                    "required": ["workspace"],
                    "additionalProperties": False,
                },
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


def test_register_and_get_manifest() -> None:
    registry = PluginRegistry()
    manifest = make_manifest()

    registered = registry.register(manifest)

    assert registered == manifest
    assert registry.get(manifest.plugin_id) == manifest
    assert registry.has_plugin(manifest.plugin_id)


def test_register_same_manifest_is_idempotent() -> None:
    registry = PluginRegistry()
    manifest = make_manifest()

    first = registry.register(manifest)
    second = registry.register(manifest)

    assert first == second
    assert len(registry.list_plugins()) == 1


def test_conflicting_duplicate_plugin_id_is_rejected() -> None:
    registry = PluginRegistry()
    registry.register(make_manifest())

    with pytest.raises(PluginAlreadyRegisteredError, match="different manifest"):
        registry.register(make_manifest(version="2.0.0"))


def test_non_manifest_registration_is_rejected() -> None:
    registry = PluginRegistry()

    with pytest.raises(TypeError, match="PluginManifest"):
        registry.register({"plugin_id": "not-a-manifest"})  # type: ignore[arg-type]


def test_get_unknown_plugin_raises_typed_error() -> None:
    with pytest.raises(PluginNotFoundError, match="not registered"):
        PluginRegistry().get("missing.plugin")


def test_get_unknown_capability_raises_typed_error() -> None:
    registry = PluginRegistry()
    registry.register(make_manifest())

    with pytest.raises(CapabilityNotFoundError, match="not declared"):
        registry.get_capability("example.file-tools", "delete_files")


def test_get_capability_includes_plugin_identity() -> None:
    registry = PluginRegistry()
    registry.register(make_manifest())

    result = registry.get_capability("example.file-tools", "list_files")

    assert result.plugin_id == "example.file-tools"
    assert result.plugin_version == "1.0.0"
    assert result.capability.name == "list_files"


def test_plugin_and_capability_listing_is_deterministic() -> None:
    registry = PluginRegistry()
    registry.register(make_manifest(plugin_id="zeta.tools"))
    registry.register(make_manifest(plugin_id="alpha.tools", capability_name="read_files"))

    assert [item.plugin_id for item in registry.list_plugins()] == [
        "alpha.tools",
        "zeta.tools",
    ]
    assert [item.plugin_id for item in registry.list_capabilities()] == [
        "alpha.tools",
        "zeta.tools",
    ]


def test_list_capabilities_for_unknown_plugin_raises() -> None:
    with pytest.raises(PluginNotFoundError):
        PluginRegistry().list_capabilities("missing.plugin")


def test_has_capability_reports_presence() -> None:
    registry = PluginRegistry()
    registry.register(make_manifest())

    assert registry.has_capability("example.file-tools", "list_files")
    assert not registry.has_capability("example.file-tools", "delete_files")
    assert not registry.has_capability("missing.plugin", "list_files")


def test_unregister_removes_plugin_and_returns_copy() -> None:
    registry = PluginRegistry()
    manifest = make_manifest()
    registry.register(manifest)

    removed = registry.unregister(manifest.plugin_id)

    assert removed == manifest
    assert not registry.has_plugin(manifest.plugin_id)
    with pytest.raises(PluginNotFoundError):
        registry.get(manifest.plugin_id)


def test_unregister_unknown_plugin_raises() -> None:
    with pytest.raises(PluginNotFoundError):
        PluginRegistry().unregister("missing.plugin")


def test_registry_defensively_copies_nested_schema_data() -> None:
    registry = PluginRegistry()
    manifest = make_manifest()
    registry.register(manifest)

    manifest.capabilities[0].input_schema["properties"]["workspace"]["type"] = "integer"
    retrieved = registry.get(manifest.plugin_id)
    retrieved.capabilities[0].input_schema["properties"]["workspace"]["type"] = "boolean"

    stored = registry.get(manifest.plugin_id)
    assert stored.capabilities[0].input_schema["properties"]["workspace"]["type"] == "string"


def test_concurrent_identical_registration_is_safe() -> None:
    registry = PluginRegistry()
    manifest = make_manifest()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(registry.register, [manifest] * 16))

    assert all(result == manifest for result in results)
    assert len(registry.list_plugins()) == 1
