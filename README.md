# Universal Automation Engine

A modular, API-first automation engine designed to expose reusable automation capabilities through REST APIs and compatible AI integrations using the Model Context Protocol (MCP).

## Project status

**Phase 1 — Project foundation** is in progress. The initial scope establishes architecture, packaging, development standards, tests, and continuous integration. No hosted service or production deployment is included.

## Project principles

- One automation engine, multiple integration interfaces.
- Automation modules use a documented, versioned plugin contract.
- REST and MCP interfaces delegate to the same core services.
- Secure-by-default execution with explicit permissions and approvals for sensitive actions.
- Free and open-source development tooling wherever practical.

## Integration interfaces

- REST API: see [API Reference](docs/API_REFERENCE.md).
- MCP server: see [MCP Integration](docs/MCP_INTEGRATION.md). Install the optional `mcp` extra to enable MCP support.
- Plugin contract: see [Plugin Contract](docs/PLUGIN_CONTRACT.md).
- Built-in file tools: see [File Automation](docs/FILE_AUTOMATION.md).

## Planned initial capabilities

1. File automation
2. Document automation
3. Structured data processing

## Development

The project targets Python 3.12 or newer. Setup and contribution instructions will be documented as the foundation is established.

## Status

This repository is an early-stage project. Interfaces and implementation details may evolve before the first stable release.
