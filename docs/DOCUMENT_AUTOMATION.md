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
| create_pdf_document | .pdf | documents.create |
| create_docx_document | .docx | documents.create |
| create_xlsx_document | .xlsx | documents.create |

The PDF, DOCX, and XLSX tools are registered only when their optional libraries are installed.

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

Install office-format support with:

~~~bash
python -m pip install -e ".[documents]"
~~~

The optional extra provides ReportLab, python-docx, and openpyxl. REST-only or file-only installations do not need these libraries.

## Safety controls

- Only .md, .txt, .json, .pdf, .docx, and .xlsx output extensions are accepted when the corresponding format capability is installed.
- Absolute paths, parent traversal, and symbolic links are rejected.
- Parent directories must already exist; the module does not create directories.
- New files are created exclusively; existing files are never overwritten.
- File creation uses exclusive OS-level creation flags.
- Output is capped by max_output_bytes (default 1 MiB).
- Files are created with owner-only permissions where supported by the host operating system.
- All capabilities require documents.create.
- No update, rename, move, or delete capability is included.

Creating a new file is additive, not destructive. The host must still grant the documents.create permission to the caller.

## PDF, Word, and Excel documents

- PDF output uses ReportLab Platypus. Title and paragraph text is XML-escaped before rendering.
- DOCX output uses python-docx and stores plain-text paragraphs in a new Word document.
- XLSX output uses openpyxl. User-provided string cells are explicitly stored as text, so values beginning with formula-like characters are not interpreted as spreadsheet formulas.
- Excel worksheets support up to 50 columns and 10,000 data rows. Each row must match the header count.
- Worksheet names must meet Excel's 31-character and forbidden-character rules.
- PDF uses ReportLab's default font set; specialized Unicode font embedding is not included yet.

## JSON documents

JSON documents are formatted with indentation and UTF-8 encoding. Non-finite numbers such as NaN and Infinity are rejected.

## Using through REST and MCP

Once registered, all three capabilities appear automatically through:

- REST plugin/capability discovery and POST /v1/executions.
- MCP tools/list discovery and tool calls.

No separate application or UI is required.

## Current limitations

- No image generation or advanced document layouts.
- No file overwrite or update.
- No directory creation.
- No binary output or streaming.
- No external storage integrations.
