# Universal Automation Engine — Project Status

**Status date:** 2026-11-20  
**Current release line:** 0.1.0 (pre-release)  
**Default branch:** `main`  
**Current baseline commit:** `d1ab949f18ae8fd80af19b9c741903c0f79f006b`

## Executive summary

Universal Automation Engine (UAE) is a modular, API-first Python automation engine. Its REST and Model Context Protocol (MCP) interfaces expose the same registered capabilities through a shared execution core.

The repository has completed its initial foundation and currently contains:

- Python package structure and CI for Python 3.12 and 3.13.
- Plugin contracts and a plugin registry.
- Capability execution and permission/approval policy primitives.
- FastAPI REST interface and an MCP adapter.
- Shared workspace path guard.
- Read-only file automation.
- New Markdown, text, JSON, PDF, DOCX, and XLSX document creation (office/PDF formats use optional dependencies).
- Bounded CSV/JSON reading and writing, JSON record transformations, and optional XLSX extraction.
- Sequential workflow orchestration with versioned contracts, field mappings, conditions, per-step authorization, and compensation.
- Managed API-key lifecycle with high-entropy issuance, SHA-256 digest storage, expiry, rotation, revocation, and REST integration.
- Unit, API, MCP, and integration test suites.

This is an implemented development baseline, **not yet a production-ready or stable v1.0 release**.

## Current implementation snapshot

| Area | Current state | Notes |
|---|---|---|
| Packaging and CI | Implemented | Python 3.12/3.13 CI matrix; Ruff and pytest |
| Plugin contract | Implemented | Versioned manifests and capability schemas |
| Registry | Implemented | Registration and discovery |
| Capability execution | Implemented | In-process handler execution |
| Security policy | Initial implementation | Permission checks and request-bound approval-grant validation primitives |
| REST API | Initial implementation | Managed API-key lifecycle available; default store is in-memory; static mapping retained for compatibility |
| MCP adapter | Initial implementation | Local stdio and optional authenticated remote transport |
| File automation | Initial implementation | Workspace-confined, read-only file operations |
| Document creation | Initial implementation | New-file creation; no overwrite/update/delete |
| Structured data module | Initial implementation | Bounded CSV/JSON operations, record transforms, optional XLSX extraction |
| Workflow orchestration | Initial implementation | Sequential in-memory runs; no persistence, queue, parallel execution, or automatic retries |
| Persistent execution history | Not implemented | No durable run store |
| Production deployment | Not implemented | Deliberately outside the initial foundation |

## Known limitations and risks

1. Execution is synchronous/in-process; no general sandbox or hard execution timeout is provided.
2. Managed API-key issuance, expiry, rotation, and revocation are available, but the default store is in-memory; hosts must provide a persistent APIKeyStore for durable or multi-process deployments.
3. Approval validation primitives exist, but there is no built-in approval request, decision, storage, or reviewer workflow.
4. There is no persistent workflow definition or execution-history store.
5. Third-party plugin discovery/loading and isolation are not implemented.
6. MCP remote authentication depends on host-provided identity/token verification; the engine does not provide an identity provider.
7. Existing file/document capabilities are intentionally constrained; they do not provide general file editing, deletion, or arbitrary filesystem access.
8. Passing CI demonstrates the configured checks, not production readiness, security certification, or deployment suitability.

## Delivery status

| Batch | Scope | Status |
|---|---|---|
| 1 | Repository consolidation and project governance | Complete |
| 2 | Structured data automation | Complete |
| 3 | Workflow orchestration | Complete |
| 4 | Authentication, authorization, and approval hardening | Not started |
| 5 | Execution reliability and isolation | Not started |
| 6 | Additional automation modules | Not started |
| 7 | REST/MCP integration maturity | Not started |
| 8 | Documentation and developer experience | In progress |
| 9 | Final validation and v1.0 release | Not started |

See [the implementation roadmap](docs/ROADMAP.md) for deliverables and exit criteria.

## Working rules

- Develop in small, isolated feature branches based on the latest `main`.
- Do not merge until code review and required CI checks pass.
- Do not deploy, introduce paid services, or perform destructive repository/database actions without explicit approval.
- Keep security-sensitive capabilities denied by default until a trusted authorization/approval path exists.
- Update this status document and the roadmap as batches are completed.
- Treat GitHub Issues as the project backlog and source of truth for implementation tasks.

## Definition of v1.0 completion

A v1.0 release requires the core engine, REST and MCP interfaces, file/document/data capabilities, multi-step workflows, robust security and execution controls, documented installation and extension paths, and passing automated validation. The exact release gate is recorded in [the roadmap](docs/ROADMAP.md).

Production hosting is not a prerequisite for v1.0; the engine must be installable and self-hostable without paid infrastructure.
