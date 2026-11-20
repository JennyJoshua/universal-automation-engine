# Document Automation Module

## Overview

The first document-generation module creates new Markdown, plain-text, and JSON documents inside a configured workspace.

Plugin ID: uae.document-tools

Version: 0.1.0

## Capabilities

| Capability | Output | Required permission |
|---|---|---|
| create_markdown_document | .md | documents.create |
| create_text_document | .txt | documents.create |
| create_json_document | .json | documents.create |

## Registration

~~~python
from pathlib import Path

from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.documents import DocumentAutomationModule
from universal_automation.security import AuthorizationPolicy

workspace = Path("/srv/uae-workspaces/customer-a")
registry = PluginRegistry()
executor = CapabilityExecutor(registry, AuthorizationPolicy())

documents = DocumentAutomationModule(
    workspace,
    max_output_bytes=1_048_576,
)
documents.register(registry, executor)
~~~

The document module and file module can share the same workspace root, registry, and executor. Both use the shared WorkspaceGuard for path confinement.

## Safety controls

- Only .md, .txt, and .json output extensions are accepted.
- Absolute paths, parent traversal, and symbolic links are rejected.
- Parent directories must already exist; the module does not create directories.
- New files are created exclusively; existing files are never overwritten.
- File creation uses exclusive OS-level creation flags.
- Output is capped by max_output_bytes (default 1 MiB).
- Files are created with owner-only permissions where supported by the host operating system.
- All capabilities require documents.create.
- No update, rename, move, or delete capability is included.

Creating a new file is additive, not destructive. The host must still grant the documents.create permission to the caller.

## JSON documents

JSON documents are formatted with indentation and UTF-8 encoding. Non-finite numbers such as NaN and Infinity are rejected.

## Using through REST and MCP

Once registered, all three capabilities appear automatically through:

- REST plugin/capability discovery and POST /v1/executions.
- MCP tools/list discovery and tool calls.

No separate application or UI is required.

## Current limitations

- No PDF, DOCX, XLSX, or image generation yet.
- No file overwrite or update.
- No directory creation.
- No binary output or streaming.
- No external storage integrations.
