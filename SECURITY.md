# Security Policy

## Reporting a vulnerability

Please do not disclose exploitable vulnerabilities in public issues. Report them privately to the repository maintainer through GitHub's private vulnerability reporting feature, if enabled.

## Security design commitments

- Authenticate remote callers.
- Authorize each capability independently.
- Apply least-privilege permissions.
- Require explicit approval for destructive or externally consequential operations.
- Restrict filesystem access to configured working locations.
- Never execute arbitrary user-provided code in the API process.
- Keep secrets out of source control, logs, and tool outputs.
- Record security-relevant execution events.
- Apply timeouts and resource limits to module execution.

## Supported versions

Before the first stable release, the latest development branch is the only actively maintained version.
