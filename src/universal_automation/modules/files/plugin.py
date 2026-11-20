"""Workspace-confined, read-only file automation capabilities."""

from __future__ import annotations

import errno
import os
from pathlib import Path, PureWindowsPath
from typing import Any

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.execution import CapabilityExecutor, HandlerInputError
from universal_automation.core.registry import PluginRegistry


class FileAutomationModule:
    """Provide safe file discovery, UTF-8 reading, and text search in one workspace."""

    plugin_id = "uae.file-tools"

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_file_bytes: int = 1_048_576,
        max_scan_files: int = 500,
        max_scan_directories: int = 1_000,
        max_directory_entries: int = 1_000,
        max_scan_bytes: int = 10_485_760,
    ) -> None:
        try:
            root = Path(workspace_root).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("workspace_root must be an existing directory") from exc
        if not root.is_dir():
            raise ValueError("workspace_root must be an existing directory")
        if min(
            max_file_bytes,
            max_scan_files,
            max_scan_directories,
            max_directory_entries,
            max_scan_bytes,
        ) < 1:
            raise ValueError("File automation limits must all be positive")

        self._root = root
        self._max_file_bytes = max_file_bytes
        self._max_scan_files = max_scan_files
        self._max_scan_directories = max_scan_directories
        self._max_directory_entries = max_directory_entries
        self._max_scan_bytes = max_scan_bytes
        self._manifest = self._build_manifest()
        self._handlers = {
            "list_files": self._list_files,
            "read_text_file": self._read_text_file,
            "search_text_files": self._search_text_files,
        }

    @property
    def manifest(self) -> PluginManifest:
        """Return a defensive copy of this module's plugin manifest."""
        return self._manifest.model_copy(deep=True)

    def register(self, registry: PluginRegistry, executor: CapabilityExecutor) -> None:
        """Register the manifest and its trusted handlers with the shared engine."""
        if executor.plugin_registry is not registry:
            raise ValueError("File module and executor must use the same plugin registry instance")

        registry.register(self._manifest)
        for capability_name, handler in self._handlers.items():
            executor.register_handler(self.plugin_id, capability_name, handler)

    def _build_manifest(self) -> PluginManifest:
        list_files_input = {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "default": "."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100},
            },
            "additionalProperties": False,
        }
        list_files_output = {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "path": {"type": "string"},
                            "kind": {"type": "string", "enum": ["file", "directory"]},
                            "size_bytes": {"type": "integer", "minimum": 0},
                        },
                        "required": ["name", "path", "kind", "size_bytes"],
                        "additionalProperties": False,
                    },
                },
                "truncated": {"type": "boolean"},
            },
            "required": ["files", "truncated"],
            "additionalProperties": False,
        }
        read_text_input = {
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1}},
            "required": ["path"],
            "additionalProperties": False,
        }
        read_text_output = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "size_bytes": {"type": "integer", "minimum": 0},
            },
            "required": ["path", "content", "size_bytes"],
            "additionalProperties": False,
        }
        search_input = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "directory": {"type": "string", "default": "."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
            "required": ["query"],
            "additionalProperties": False,
        }
        search_output = {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "line_number": {"type": "integer", "minimum": 1},
                            "line": {"type": "string"},
                            "line_truncated": {"type": "boolean"},
                        },
                        "required": ["path", "line_number", "line", "line_truncated"],
                        "additionalProperties": False,
                    },
                },
                "truncated": {"type": "boolean"},
                "files_scanned": {"type": "integer", "minimum": 0},
            },
            "required": ["matches", "truncated", "files_scanned"],
            "additionalProperties": False,
        }

        return PluginManifest(
            plugin_id=self.plugin_id,
            display_name="Workspace File Tools",
            version="0.1.0",
            description="Read-only file discovery and text search inside a configured workspace.",
            capabilities=(
                CapabilitySpec(
                    name="list_files",
                    description="List files and directories in the configured workspace.",
                    input_schema=list_files_input,
                    output_schema=list_files_output,
                    permissions=("files.read",),
                ),
                CapabilitySpec(
                    name="read_text_file",
                    description="Read a UTF-8 text file within the configured workspace.",
                    input_schema=read_text_input,
                    output_schema=read_text_output,
                    permissions=("files.read",),
                ),
                CapabilitySpec(
                    name="search_text_files",
                    description="Search UTF-8 text files within the configured workspace.",
                    input_schema=search_input,
                    output_schema=search_output,
                    permissions=("files.read",),
                ),
            ),
        )

    def _resolve_workspace_path(self, raw_path: str) -> Path:
        """Resolve a relative path and reject traversal, absolute paths, and symlinks."""
        if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
            raise HandlerInputError("A valid workspace-relative path is required")

        relative = Path(raw_path)
        windows_path = PureWindowsPath(raw_path)
        if relative.is_absolute() or windows_path.is_absolute() or windows_path.drive:
            raise HandlerInputError("Absolute paths are not allowed")

        if any(part == ".." for part in relative.parts) or any(
            part == ".." for part in windows_path.parts
        ):
            raise HandlerInputError("Parent-directory traversal is not allowed")

        current = self._root
        for part in relative.parts:
            if part in ("", "."):
                continue
            current = current / part
            if current.is_symlink():
                raise HandlerInputError("Symbolic links are not supported")

        resolved = current.resolve(strict=False)
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise HandlerInputError("Path is outside the configured workspace") from exc

        return resolved

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self._root).as_posix() or "."

    def _list_files(self, data: dict[str, Any]) -> dict[str, Any]:
        directory = self._resolve_workspace_path(data.get("directory", "."))
        if not directory.exists():
            raise HandlerInputError("Directory was not found")
        if not directory.is_dir():
            raise HandlerInputError("The requested path is not a directory")

        max_results = data.get("max_results", 100)
        entries: list[dict[str, Any]] = []
        truncated = False

        with os.scandir(directory) as iterator:
            for scanned, entry in enumerate(iterator, start=1):
                if scanned > self._max_directory_entries:
                    truncated = True
                    break
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        kind = "file"
                        size_bytes = entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        kind = "directory"
                        size_bytes = 0
                    else:
                        continue
                except OSError:
                    continue

                entry_path = Path(entry.path)
                entries.append(
                    {
                        "name": entry.name,
                        "path": self._relative_path(entry_path),
                        "kind": kind,
                        "size_bytes": size_bytes,
                    }
                )

        entries.sort(key=lambda item: item["name"].casefold())
        if len(entries) > max_results:
            truncated = True
        return {"files": entries[:max_results], "truncated": truncated}

    def _read_text_file(self, data: dict[str, Any]) -> dict[str, Any]:
        target = self._resolve_workspace_path(data["path"])
        if not target.exists():
            raise HandlerInputError("File was not found")
        if not target.is_file():
            raise HandlerInputError("The requested path is not a file")

        try:
            descriptor = os.open(
                target,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            with os.fdopen(descriptor, "rb") as file_handle:
                raw = file_handle.read(self._max_file_bytes + 1)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise HandlerInputError("Symbolic links are not supported") from exc
            raise

        if len(raw) > self._max_file_bytes:
            raise HandlerInputError("File exceeds the configured read-size limit")

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HandlerInputError("File is not valid UTF-8 text") from exc

        return {
            "path": self._relative_path(target),
            "content": content,
            "size_bytes": len(raw),
        }

    def _search_text_files(self, data: dict[str, Any]) -> dict[str, Any]:
        directory = self._resolve_workspace_path(data.get("directory", "."))
        if not directory.exists():
            raise HandlerInputError("Directory was not found")
        if not directory.is_dir():
            raise HandlerInputError("The requested path is not a directory")

        query = data["query"].casefold()
        max_results = data.get("max_results", 50)
        matches: list[dict[str, Any]] = []
        files_scanned = 0
        bytes_scanned = 0
        directories_scanned = 0
        truncated = False

        for current, directory_names, file_names in os.walk(directory, followlinks=False):
            current_path = Path(current)
            valid_directories = [
                name
                for name in directory_names
                if not (current_path / name).is_symlink()
            ]
            if len(valid_directories) > self._max_directory_entries:
                truncated = True
                valid_directories = valid_directories[: self._max_directory_entries]
            directory_names[:] = sorted(valid_directories)
            directories_scanned += 1
            if directories_scanned > self._max_scan_directories:
                truncated = True
                break

            for file_name in sorted(file_names, key=str.casefold):
                file_path = current_path / file_name
                if file_path.is_symlink() or not file_path.is_file():
                    continue

                if files_scanned >= self._max_scan_files:
                    truncated = True
                    break
                files_scanned += 1

                try:
                    size = file_path.stat().st_size
                except OSError:
                    continue

                if size > self._max_file_bytes:
                    continue
                if bytes_scanned + size > self._max_scan_bytes:
                    truncated = True
                    break

                try:
                    descriptor = os.open(
                        file_path,
                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    )
                    with os.fdopen(descriptor, "rb") as file_handle:
                        raw = file_handle.read(self._max_file_bytes + 1)
                    if len(raw) > self._max_file_bytes:
                        continue
                    if bytes_scanned + len(raw) > self._max_scan_bytes:
                        truncated = True
                        break
                    bytes_scanned += len(raw)
                    content = raw.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                relative_path = self._relative_path(file_path)

                for line_number, line in enumerate(content.splitlines(), start=1):
                    if query not in line.casefold():
                        continue
                    if len(matches) >= max_results:
                        truncated = True
                        break
                    matches.append(
                        {
                            "path": relative_path,
                            "line_number": line_number,
                            "line": line[:1000],
                            "line_truncated": len(line) > 1000,
                        }
                    )

                if truncated:
                    break

            if truncated:
                break

        return {
            "matches": matches,
            "truncated": truncated,
            "files_scanned": files_scanned,
        }
