"""Ensure the documented minimal plugin example remains valid."""

from runpy import run_path


def test_minimal_example_manifest_is_valid() -> None:
    namespace = run_path("examples/minimal_plugin.py")
    manifest = namespace["minimal_file_plugin"]

    assert manifest.plugin_id == "example.file-tools"
    assert manifest.capabilities[0].name == "list_files"
