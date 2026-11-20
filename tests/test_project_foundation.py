"""Smoke tests for the initial project foundation."""

from universal_automation import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"


def test_version_uses_semantic_version_shape() -> None:
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
