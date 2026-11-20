# Universal Automation Engine — Implementation Roadmap

**Roadmap version:** 1.0  
**Status date:** 2026-11-20  
**Target:** A tested, documented, self-hostable v1.0 release without mandatory paid infrastructure.

This roadmap distinguishes existing implementation from planned work. Batch completion requires merged code, passing checks, reviewed documentation, and an updated project status.

## Batch 1 — Repository consolidation and project governance

**Status: Complete**

- [x] Inspect the current main-branch implementation and repository history.
- [x] Confirm the current release version and CI Python matrix.
- [x] Replace the outdated README project-status description.
- [x] Establish an authoritative project status document.
- [x] Establish this implementation roadmap and explicit v1.0 exit criteria.
- [x] Document branch/PR/release workflow and branch-retention policy.
- [x] Review stale branches and historical PRs; retain merged feature branches as historical references.
- [x] Validate README internal documentation links against the current repository tree.
- [x] Review latest baseline CI runs; latest main run passed for the configured matrix.

**Exit criteria:** The repository accurately describes what exists, what is missing, how changes are delivered, and what constitutes v1.0.

## Batch 2 — Structured data automation

**Status: Complete**

- [x] Define a data plugin contract and capability schemas.
- [x] Add safe CSV reading and writing.
- [x] Add JSON parsing, transformation, and serialization.
- [x] Add spreadsheet data extraction and processing using optional dependencies.
- [x] Support bounded filtering, sorting, projection, and validation.
- [x] Enforce file size, row, column, and output limits.
- [x] Prevent formula injection in spreadsheet exports.
- [x] Enforce workspace confinement and explicit permissions.
- [x] Expose capabilities through REST and MCP discovery/execution.
- [x] Add unit, integration, and adversarial tests.

**Exit criteria:** Supported data operations are bounded, validated, permission-controlled, documented, and available through both interfaces.

## Batch 3 — Workflow orchestration

**Status: Complete**

- [x] Define versioned workflow and step contracts.
- [x] Execute multiple registered capabilities in a deterministic sequence.
- [x] Add explicit input/output mapping between steps.
- [x] Add conditional branching with a deliberately limited expression model.
- [x] Track queued, running, succeeded, failed, and cancelled states.
- [x] Define failure, retry, and compensation semantics.
- [x] Enforce authorization independently for every step.
- [x] Add workflow validation and cycle/complexity limits.
- [x] Add integration tests covering success and failure paths.

**Exit criteria:** A validated workflow can combine existing capabilities safely, with predictable state and failure behavior.

## Batch 4 — Authentication, authorization, and approval hardening

**Status: In progress — API-key lifecycle implementation underway**

- [x] Define host-independent identity and principal lifecycle contracts.
- [x] Add secure API-key issuance, hashing, rotation, expiry, and revocation interfaces.
- [ ] Keep secret material out of logs, errors, and persisted audit events.
- [x] Define role/permission mapping without trusting client-supplied claims.
- [ ] Implement trusted approval request, reviewer decision, expiry, and one-time binding.
- [ ] Bind approval to principal, action, resource, and execution request.
- [ ] Add audit events for authorization decisions and approvals.
- [ ] Add negative tests for replay, expiry, privilege escalation, and cross-request reuse.

**Exit criteria:** Sensitive operations cannot proceed without server-verified identity, least-privilege authorization, and a valid trusted approval where required.

## Batch 5 — Execution reliability and isolation

**Status: Not started**

- [ ] Define execution deadlines and cooperative cancellation.
- [ ] Add bounded concurrency and queue/back-pressure policy.
- [ ] Enforce input, output, memory/CPU where practical, and per-run resource limits.
- [ ] Add structured execution lifecycle events and safe error reporting.
- [ ] Define idempotency and duplicate-request behavior.
- [ ] Add retry policy only for explicitly retry-safe capabilities.
- [ ] Design isolation boundary for untrusted/third-party plugins; do not imply in-process code is sandboxed.
- [ ] Add stress, cancellation, timeout, and failure-injection tests.

**Exit criteria:** The engine has explicit resource and lifecycle controls, and its trust boundary is accurately enforced and documented.

## Batch 6 — Additional automation modules

**Status: Not started; modules delivered incrementally**

Prioritised candidates:

1. Email — provider adapters, send permissions, approval for external sending, and delivery outcomes.
2. Web/HTTP — allowlisted requests, timeout/size limits, redirect controls, and SSRF protections.
3. GitHub — scoped repository/issue/PR operations with explicit write permissions and approval gates.
4. Database — parameterized, least-privilege operations; read/write separation and destructive-operation approvals.
5. Scheduling — recurring triggers, timezone handling, missed-run policy, and execution limits.
6. Notifications — provider-neutral delivery adapters and delivery status.

Each module must have a documented contract, narrow permissions, safe defaults, unit/integration tests, and REST/MCP exposure. Add only modules that fit the stable core architecture.

**Exit criteria:** A useful, maintainable set of independently testable automation modules is available without weakening core security.

## Batch 7 — REST and MCP integration maturity

**Status: Not started**

- [ ] Verify OpenAPI schemas and consistent REST error responses.
- [ ] Add interface contract tests for discovery and execution.
- [ ] Test MCP tool schemas, annotations, and error mapping against supported SDK versions.
- [ ] Validate remote MCP authentication and principal mapping with a host verifier.
- [ ] Document transport security, host/origin allowlists, and deployment requirements.
- [ ] Add compatibility tests and pin/test supported dependency ranges.
- [ ] Provide examples for local and remote integration.

**Exit criteria:** REST and MCP expose the same capabilities consistently and securely, with repeatable compatibility tests.

## Batch 8 — Documentation and developer experience

**Status: In progress**

- [ ] Keep README and project status current.
- [ ] Complete clean-install instructions for core, development, MCP, and document extras.
- [ ] Document configuration and environment variables.
- [ ] Provide a minimal end-to-end REST example.
- [ ] Provide a minimal local MCP example and remote-host integration guidance.
- [ ] Document plugin authoring, testing, permissions, and version compatibility.
- [ ] Add workflow authoring and troubleshooting guides.
- [ ] Verify every internal documentation link and runnable example.

**Exit criteria:** A new developer can install, configure, run, test, and extend the engine from repository documentation.

## Batch 9 — Final validation and v1.0 release

**Status: Not started**

- [ ] Review architecture and dependency/security posture.
- [ ] Run complete unit, integration, API, and MCP test suites.
- [ ] Validate supported Python versions from clean environments.
- [ ] Validate core-only installation and each optional extra.
- [ ] Build and inspect the distributable package.
- [ ] Run static analysis and dependency vulnerability checks where free tooling permits.
- [ ] Resolve all release-blocking defects and document accepted limitations.
- [ ] Verify installation and examples from a clean checkout.
- [ ] Update changelog, version, README, and release notes.
- [ ] Tag and publish v1.0 only after the release gate is satisfied.

**Exit criteria:** The package is reproducibly installable, tested, documented, and released with known limitations clearly stated.

## Release gate — v1.0

The release is blocked until all of the following are true:

- Core contracts, registry, execution, and workspace boundaries are covered by tests.
- REST and MCP interfaces pass their contract and integration tests.
- File, document, and structured-data modules work within documented limits.
- Multi-step workflows enforce per-step authorization and have predictable failure semantics.
- Authentication, permissions, approvals, and audit events meet the documented security model.
- Execution deadlines, cancellation, concurrency, and resource limits are implemented and tested.
- Installation, configuration, plugin authoring, and integration documentation is complete.
- Supported Python-version CI is green.
- No known release-blocking security or correctness defects remain.
- Release notes state limitations and deployment responsibilities honestly.

## Delivery discipline

- One manageable batch or isolated sub-batch per pull request.
- Branch from current `main`; avoid parallel branches that modify the same files.
- CI must pass and changes must be reviewed before merge.
- No direct commits to `main` for implementation work.
- No paid service, production deployment, destructive operation, or material scope change without owner approval.
- Do not delete historical branches merely because their PRs have merged; retain them until their value and divergence have been reviewed.
