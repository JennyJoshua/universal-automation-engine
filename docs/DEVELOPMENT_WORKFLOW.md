# Development and Release Workflow

## Branching

- Treat `main` as the stable integration branch.
- Create a short-lived branch from the latest `main` for each isolated batch, for example `batch2/structured-data-csv-json`.
- Keep pull requests focused and avoid overlapping changes across active branches.
- Do not commit implementation changes directly to `main`.
- Historical merged feature branches are retained until reviewed; branch deletion is not an automatic cleanup step.

## Pull requests

Every pull request should include:

1. Purpose and scope.
2. Summary of implementation.
3. Security and compatibility considerations.
4. Tests added or updated and their results.
5. Documentation changes.
6. Known limitations and follow-up work.

Before merge:

- Review the complete diff, not only the PR description.
- Confirm no secrets, generated artifacts, or unrelated changes are included.
- Confirm required CI checks pass.
- Resolve review findings.
- Confirm the PR targets the current `main`.

## CI and quality

The current CI workflow tests Python 3.12 and 3.13, runs Ruff, and runs pytest with the development, MCP, and document optional dependencies installed.

Batch-specific tests should cover both success and denied/invalid cases. Optional dependency behavior must also be tested so the core package remains usable without optional integrations.

## Releases

- Use semantic versioning once public compatibility expectations are established.
- Keep unreleased changes documented.
- Do not publish a stable release while roadmap release gates remain open.
- Tag a release only after a clean package build, supported-version tests, and documentation review.
- State optional extras, platform assumptions, and known limitations in release notes.

## Owner approval gates

Explicit owner approval is required before:

- Merging a change that materially changes approved project scope.
- Production deployment or public service activation.
- Introducing paid services, subscriptions, or upgrades.
- Destructive repository, data, or infrastructure operations.
- Hosted database migrations or irreversible data changes.

Routine implementation, tests, reviews, documentation, and isolated pull requests may proceed within the approved project scope.
