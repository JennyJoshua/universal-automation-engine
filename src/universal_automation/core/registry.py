"""Thread-safe in-memory registry for validated automation plugin manifests."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from universal_automation.core.contracts import CapabilitySpec, PluginManifest


class PluginRegistryError(Exception):
    """Base exception for plugin registry operations."""


class PluginAlreadyRegisteredError(PluginRegistryError):
    """Raised when a conflicting manifest uses an existing plugin identifier."""


class PluginNotFoundError(PluginRegistryError):
    """Raised when a requested plugin is not registered."""


class CapabilityNotFoundError(PluginRegistryError):
    """Raised when a requested capability is not declared by a plugin."""


@dataclass(frozen=True, slots=True)
class RegisteredCapability:
    """A capability paired with the identity and version of its owning plugin."""

    plugin_id: str
    plugin_version: str
    capability: CapabilitySpec


class PluginRegistry:
    """Store and discover plugin metadata without loading or executing plugin code.

    All public operations are synchronized. Manifests and capabilities are copied
    on ingress and egress so callers cannot mutate registry-owned nested schemas.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._lock = RLock()

    def register(self, manifest: PluginManifest) -> PluginManifest:
        """Register a manifest, allowing an identical repeated registration."""
        if not isinstance(manifest, PluginManifest):
            raise TypeError("manifest must be a validated PluginManifest instance")

        stored_copy = manifest.model_copy(deep=True)
        with self._lock:
            existing = self._plugins.get(manifest.plugin_id)
            if existing is not None:
                if existing == manifest:
                    return existing.model_copy(deep=True)
                raise PluginAlreadyRegisteredError(
                    f"Plugin '{manifest.plugin_id}' is already registered "
                    "with a different manifest"
                )

            self._plugins[manifest.plugin_id] = stored_copy
            return stored_copy.model_copy(deep=True)

    def unregister(self, plugin_id: str) -> PluginManifest:
        """Remove a registered plugin and return a defensive copy of its manifest."""
        with self._lock:
            manifest = self._plugins.pop(plugin_id, None)
            if manifest is None:
                raise PluginNotFoundError(f"Plugin '{plugin_id}' is not registered")
            return manifest.model_copy(deep=True)

    def get(self, plugin_id: str) -> PluginManifest:
        """Return a defensive copy of a registered plugin manifest."""
        with self._lock:
            manifest = self._plugins.get(plugin_id)
            if manifest is None:
                raise PluginNotFoundError(f"Plugin '{plugin_id}' is not registered")
            return manifest.model_copy(deep=True)

    def get_capability(self, plugin_id: str, capability_name: str) -> RegisteredCapability:
        """Find one capability by its owning plugin and declared name."""
        with self._lock:
            manifest = self._plugins.get(plugin_id)
            if manifest is None:
                raise PluginNotFoundError(f"Plugin '{plugin_id}' is not registered")

            for capability in manifest.capabilities:
                if capability.name == capability_name:
                    return RegisteredCapability(
                        plugin_id=manifest.plugin_id,
                        plugin_version=manifest.version,
                        capability=capability.model_copy(deep=True),
                    )

            raise CapabilityNotFoundError(
                f"Capability '{capability_name}' is not declared by plugin '{plugin_id}'"
            )

    def list_plugins(self) -> tuple[PluginManifest, ...]:
        """Return all registered manifests in deterministic plugin-ID order."""
        with self._lock:
            return tuple(
                self._plugins[plugin_id].model_copy(deep=True)
                for plugin_id in sorted(self._plugins)
            )

    def list_capabilities(self, plugin_id: str | None = None) -> tuple[RegisteredCapability, ...]:
        """List capabilities, optionally restricted to one registered plugin."""
        with self._lock:
            if plugin_id is not None:
                manifest = self._plugins.get(plugin_id)
                if manifest is None:
                    raise PluginNotFoundError(f"Plugin '{plugin_id}' is not registered")
                manifests = (manifest,)
            else:
                manifests = tuple(self._plugins[key] for key in sorted(self._plugins))

            capabilities = [
                RegisteredCapability(
                    plugin_id=manifest.plugin_id,
                    plugin_version=manifest.version,
                    capability=capability.model_copy(deep=True),
                )
                for manifest in manifests
                for capability in sorted(manifest.capabilities, key=lambda item: item.name)
            ]
            return tuple(capabilities)

    def has_plugin(self, plugin_id: str) -> bool:
        """Return whether a plugin identifier is registered."""
        with self._lock:
            return plugin_id in self._plugins

    def has_capability(self, plugin_id: str, capability_name: str) -> bool:
        """Return whether a plugin declares the requested capability."""
        with self._lock:
            manifest = self._plugins.get(plugin_id)
            return manifest is not None and any(
                capability.name == capability_name for capability in manifest.capabilities
            )
