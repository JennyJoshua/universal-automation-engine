# Architecture Overview

## Purpose

Universal Automation Engine (UAE) is a modular automation core exposed through multiple interfaces. It is not intended to require a dedicated end-user application.

## Architectural principles

1. **Core-first:** business logic belongs in the engine, not in transport adapters.
2. **Interface independence:** REST, MCP, and future adapters call the same application services.
3. **Explicit plugin contract:** every module declares identity, version, capabilities, schemas, and required permissions.
4. **Secure by default:** validate inputs, authorize every operation, isolate execution, and record outcomes.
5. **Incremental delivery:** add capabilities through small, independently tested modules.

## Logical layers

- **Interfaces:** REST API and MCP adapters translate external requests into application commands.
- **Security:** authentication, authorization, approval policies, secret handling, and execution isolation.
- **Core:** plugin registry, task lifecycle, orchestration, execution coordination, and common result types.
- **Modules:** independently versioned automation capabilities such as files, documents, and structured data.
- **Adapters:** controlled connections to storage, databases, and external services.

## Request lifecycle

1. Receive and validate a request.
2. Authenticate the caller at the interface boundary.
3. Resolve the requested capability through the registry.
4. Check permissions and whether approval is required.
5. Execute through a controlled module interface.
6. Record the outcome and return a structured result.

## Non-goals for Phase 1

- No production deployment or hosted service.
- No arbitrary user-supplied code execution.
- No payment, subscription, or billing system.
- No requirement for a separate frontend.
- No database migration or hosted database dependency.

## Initial implementation sequence

Project packaging and CI → plugin contract → registry → execution engine → security policies → REST API → MCP adapter → first-party modules.
