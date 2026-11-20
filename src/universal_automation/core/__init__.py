"""Core orchestration and plugin contracts for the automation engine."""

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.registry import (
    CapabilityNotFoundError,
    PluginAlreadyRegisteredError,
    PluginNotFoundError,
    PluginRegistry,
    PluginRegistryError,
    RegisteredCapability,
)

__all__ = [
    "CapabilityNotFoundError",
    "CapabilitySpec",
    "PluginAlreadyRegisteredError",
    "PluginManifest",
    "PluginNotFoundError",
    "PluginRegistry",
    "PluginRegistryError",
    "RegisteredCapability",
]
