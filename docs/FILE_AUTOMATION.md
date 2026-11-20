# File Automation Module

## Overview

The first built-in module is a read-only file toolset. It operates only inside a workspace directory explicitly selected by the host application.

Plugin ID: uae.file-tools

Version: 0.1.0

## Capabilities

| Capability | Purpose | Required permission |
|---|---|---|
| list_files | List files and directories | files.read |
| read_text_file | Read a UTF-8 text file | files.read |
| search_text_files | Search UTF-8 text files | files.read |

All three capabilities are read-only. The initial module does not create, modify, rename, move, or delete files.

## Registration

~~~python
from pathlib import Path

from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.files import FileAutomationModule
from universal_automation.security import AuthorizationPolicy

workspace = Path("/srv/uae-workspaces/customer-a")
registry = PluginRegistry()
executor = CapabilityExecutor(registry, AuthorizationPolicy())

file_tools = FileAutomationModule(
    workspace,
    max_file_bytes=1_048_576,
    max_scan_files=500,
    max_scan_directories=1_000,
    max_directory_entries=1_000,
    max_scan_bytes=10_485_760,
)
file_tools.register(registry, executor)
~~~

The host must choose the workspace root. Do not accept a workspace root from an untrusted tool-call argument.

## Safety controls

- Absolute paths and Windows drive paths are rejected.
- Parent-directory traversal (..) is rejected.
- Symbolic links are rejected for direct reads and omitted from directory listings/search.
- File reads are capped by max_file_bytes.
- Search is capped by file count, directory count, total bytes, and result count.
- Binary/non-UTF-8 files are skipped during search and rejected by text reads.
- Search result lines are truncated to 1,000 characters.
- All capabilities require the files.read permission.
- Expected file/path errors use safe HandlerInputError messages rather than exposing filesystem internals.

## Default limits

| Limit | Default |
|---|---:|
| Maximum bytes per file read | 1 MiB |
| Maximum files scanned | 500 |
| Maximum directories scanned | 1,000 |
| Maximum entries listed per directory | 1,000 |
| Maximum total search bytes | 10 MiB |
| Maximum list/search results | 100 |

Limits can be changed by trusted host configuration. Keep them conservative when exposing the module to remote callers.

## Using through REST and MCP

Once registered, the same capabilities automatically appear in:

- REST: GET /v1/capabilities and POST /v1/executions.
- MCP: dynamic tools/list discovery and tool calls.

No separate UI or duplicate implementation is required.

## Current limitations

- Text-only UTF-8 reads; no binary file conversion.
- No uploads or downloads.
- No file modifications or destructive operations.
- No streaming for large files.
- No cross-workspace access within one module instance.
- Filesystem permissions of the host process still apply.
