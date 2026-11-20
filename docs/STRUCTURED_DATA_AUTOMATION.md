# Structured Data Automation Module

## Overview

The structured-data module provides bounded CSV and JSON operations, record transformation, and optional XLSX extraction. It uses the same plugin registry and executor as the REST and MCP interfaces.

Plugin ID: `uae.structured-data`

Version: `0.1.0`

## Capabilities

| Capability | Purpose | Permission |
|---|---|---|
| `read_csv` | Read UTF-8 CSV records and headers | `files.read` |
| `write_csv` | Create a new CSV file | `data.create` |
| `read_json` | Parse a JSON file | `files.read` |
| `write_json` | Serialize JSON to a new file | `data.create` |
| `transform_records` | Filter, sort, project, and limit JSON records | `data.transform` |
| `read_spreadsheet` | Read an XLSX worksheet (optional) | `files.read` |

The module never overwrites existing files. CSV and JSON writes use the shared workspace guard and exclusive new-file creation. XLSX support is registered only when the optional `openpyxl` dependency is installed.

## Registration

~~~python
from pathlib import Path

from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.modules.data import StructuredDataModule
from universal_automation.security import AuthorizationPolicy

workspace = Path("/srv/uae-workspaces/customer-a")
registry = PluginRegistry()
executor = CapabilityExecutor(registry, AuthorizationPolicy())

data_tools = StructuredDataModule(
    workspace,
    max_file_bytes=2_097_152,
    max_output_bytes=2_097_152,
    max_rows=10_000,
    max_columns=50,
)
data_tools.register(registry, executor)
~~~

Grant only the permissions required by the caller. Reading requires `files.read`; file creation requires `data.create`; in-memory record transformations require `data.transform`.

## Safety and limits

- All file paths are relative to a host-selected workspace.
- Absolute paths, traversal, and symbolic links are rejected by the shared workspace guard.
- File reads and output files are byte-limited.
- CSV and spreadsheet rows and columns are bounded.
- CSV headers must be non-empty and unique; malformed or inconsistent rows are rejected.
- JSON must parse and serialize without non-standard NaN or Infinity values.
- CSV exports prefix formula-like text cells with an apostrophe to reduce spreadsheet formula-injection risk. Numeric values remain numeric.
- XLSX extraction uses read-only mode, cached values, and bounded row/column iteration.
- Writes create new files only; overwrite, edit, and delete operations are not provided.

Default limits are 2 MiB per input/output file, 10,000 rows, and 50 columns. Trusted hosts may lower these values. Hard maximums are enforced for rows and columns.

## Record transformation

`transform_records` accepts a JSON array of objects and optional:

- `filters`: exact key/value matches (all supplied filters must match).
- `sort_by` and `descending`: deterministic field sorting.
- `columns`: field projection.
- `limit`: maximum returned records.

This is deliberately a small transformation model; it does not evaluate expressions or execute user-supplied code.

## REST and MCP

After registration, the capabilities are automatically discoverable through the shared REST capability endpoints and MCP tool listing. No separate transport-specific implementation is required.
