# Contributing

Thank you for helping improve Universal Automation Engine.

## Before contributing

1. Read [the architecture overview](docs/ARCHITECTURE.md).
2. Check existing issues before starting substantial work.
3. For significant changes, open or discuss an issue first.

## Pull request expectations

- Keep each pull request focused.
- Include or update automated tests.
- Update documentation when behavior or public interfaces change.
- Run `ruff check .` and `pytest` locally.
- Explain security, compatibility, and migration implications where relevant.

## Plugin contributions

Plugin modules must use the documented plugin contract once that contract is introduced. Modules must declare their capabilities, input/output schemas, and permission requirements. They must not bypass the engine's authorization or execution controls.

## Scope control

Do not introduce paid services, production deployments, destructive repository operations, or major scope changes without maintainer approval.
