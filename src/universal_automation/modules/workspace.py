"""Shared workspace confinement and safe file access primitives."""

from __future__ import annotations

import errno
import os
from pathlib import Path, PureWindowsPath

from universal_automation.core.execution import HandlerInputError


class WorkspaceGuard:
    """Confine file access to one trusted root and reject path/symlink escapes."""

    def __init__(self, workspace_root: str | Path) -> None:
        try:
            root = Path(workspace_root).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("workspace_root must be an existing directory") from exc
        if not root.is_dir():
            raise ValueError("workspace_root must be an existing directory")
        self._root = root

    @property
    def root(self) -> Path:
        """Return the canonical workspace root."""
        return self._root

    def resolve_relative_path(self, raw_path: str) -> Path:
        """Resolve a workspace-relative path, rejecting absolute and symlink paths."""
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

    def relative_path(self, path: Path) -> str:
        """Convert a verified workspace path into a portable relative path."""
        try:
            return path.relative_to(self._root).as_posix() or "."
        except ValueError as exc:
            raise HandlerInputError("Path is outside the configured workspace") from exc

    def read_bytes(self, raw_path: str, *, max_bytes: int) -> bytes:
        """Read a bounded regular file without following a final symbolic link."""
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")

        target = self.resolve_relative_path(raw_path)
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
                raw = file_handle.read(max_bytes + 1)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise HandlerInputError("Symbolic links are not supported") from exc
            raise

        if len(raw) > max_bytes:
            raise HandlerInputError("File exceeds the configured read-size limit")
        return raw

    def create_new_file(
        self,
        raw_path: str,
        content: bytes,
        *,
        max_bytes: int,
    ) -> Path:
        """Create a new file exclusively; never overwrite an existing path."""
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        if len(content) > max_bytes:
            raise HandlerInputError("Document exceeds the configured output-size limit")

        target = self.resolve_relative_path(raw_path)
        if target == self._root:
            raise HandlerInputError("A file path is required")
        if not target.parent.exists():
            raise HandlerInputError("Parent directory was not found")
        if not target.parent.is_dir():
            raise HandlerInputError("Parent path is not a directory")
        if target.exists():
            raise HandlerInputError("File already exists; overwriting is not supported")

        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(target, flags, 0o600)
            with os.fdopen(descriptor, "wb") as file_handle:
                file_handle.write(content)
                file_handle.flush()
        except FileExistsError as exc:
            raise HandlerInputError(
                "File already exists; overwriting is not supported"
            ) from exc
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise HandlerInputError("Symbolic links are not supported") from exc
            raise

        return target
