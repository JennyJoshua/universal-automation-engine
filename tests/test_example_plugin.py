"""Ensure the documented minimal plugin example remains valid."""

from examples.minimal_plugin import minimal_file_plugin


def test_minimal_example_manifest_is_valid() -> None:
    assert minimal_file_plugin.plugin_id == "example.file-tools"
    assert minimal_file_plugin.capabilities[0].name == "list_files"
