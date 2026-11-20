# Universal Automation Engine

A modular, API-first Python automation engine that exposes reusable automation capabilities through a shared execution core, REST API, and Model Context Protocol (MCP) interface.

> **Project status:** Active development, pre-release (version `0.1.0`). The core foundation, plugin registry, capability execution, REST/MCP adapters, workspace-confined file operations, and document creation are implemented. The engine is **not yet a stable v1.0 or production-ready release**.

## What exists today

- Versioned plugin and capability contracts.
- Plugin registry and capability discovery.
- Shared capability execution and permission/approval policy primitives.
- FastAPI REST interface.
- MCP adapter for compatible clients.
- Workspace-confined, read-only file automation.
- New Markdown, text, JSON, PDF, DOCX, and XLSX document creation.
- Bounded CSV/JSON data operations, record transformations, and optional XLSX extraction.
- Sequential, validated workflows with explicit mappings, conditions, authorization, and compensation.\n- Managed API-key issuance, hashed storage, expiry, rotation, revocation, and REST authentication.
- Automated tests and CI for Python 3.12 and 3.13.

See [Project Status](PROJECT_STATUS.md) for the verified implementation snapshot and known limitations.

## Integration interfaces

- [REST API reference](docs/API_REFERENCE.md)
- [MCP integration guide](docs/MCP_INTEGRATION.md)
- [Plugin contract](docs/PLUGIN_CONTRACT.md)
- [Plugin registry](docs/PLUGIN_REGISTRY.md)
- [Capability execution](docs/CAPABILITY_EXECUTION.md)
- [File automation](docs/FILE_AUTOMATION.md)
- [Document automation](docs/DOCUMENT_AUTOMATION.md)
- [Structured data automation](docs/STRUCTURED_DATA_AUTOMATION.md)
- [Workflow orchestration](docs/WORKFLOW_ORCHESTRATION.md)

## Installation

The project targets Python 3.12 or newer.

Install the package with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Install optional integrations as needed:

```bash
# MCP server support
python -m pip install -e ".[mcp]"

# PDF, Word, and Excel document generation
# Structured data XLSX extraction
python -m pip install -e ".[documents]"

# All current optional integrations for development/testing
python -m pip install -e ".[dev,mcp,documents]"
```

See [Development Guide](docs/DEVELOPMENT.md) for setup and testing details.

## Current limitations

- Capability handlers execute in-process; a general plugin sandbox and hard execution timeout are not yet provided.
- REST API keys and principals are supplied by the host in memory; key issuance, rotation, and revocation are not included.
- Approval policy primitives exist, but there is no built-in approval request/reviewer workflow.
- Workflow orchestration and persistent execution history are not yet implemented.
- Remote MCP authentication requires a host-provided trusted token verifier.
- File and document capabilities are deliberately constrained and do not provide general file editing or deletion.

Do not expose the engine to untrusted users or run untrusted plugin code as though it were sandboxed. Review the [Security Policy](SECURITY.md) and [Execution Security Policy](docs/SECURITY_POLICY.md) before integrating capabilities.

## Roadmap

The planned delivery path is:

1. Repository consolidation and governance.
2. Structured data automation.
3. Multi-step workflow orchestration.
4. Authentication, authorization, and approval hardening.
5. Execution reliability and isolation.
6. Additional automation modules.
7. REST and MCP integration maturity.
8. Documentation and developer experience.
9. Final validation and v1.0 release.

The detailed, acceptance-based plan is in [docs/ROADMAP.md](docs/ROADMAP.md). Development and release conventions are in [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md).

## Project principles

- One automation engine, multiple integration interfaces.
- Core business logic remains independent of REST and MCP transports.
- Modules declare capabilities, schemas, and required permissions.
- Secure defaults, least privilege, and explicit approval for sensitive operations.
- Free and open-source tooling wherever practical.
- Small, independently reviewed changes with automated tests.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [Development Workflow](docs/DEVELOPMENT_WORKFLOW.md).