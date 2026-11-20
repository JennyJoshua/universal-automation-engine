# Development Guide

## Requirements

- Python 3.12 or newer
- Git
- A virtual environment

## Local setup

```bash
git clone https://github.com/JennyJoshua/universal-automation-engine.git
cd universal-automation-engine
python -m venv .venv
```

Activate the environment:

- Linux/macOS: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Install the project and development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quality checks

```bash
ruff check .
pytest
```

## Development rules

- Keep core logic independent of REST and MCP transports.
- Add tests with every behavior change.
- Validate all external input with explicit schemas.
- Do not commit credentials, tokens, private keys, or local environment files.
- Keep changes focused and submit them through pull requests.
- Do not add paid dependencies or hosted infrastructure without approval.

## Current status

Phase 1 establishes packaging, documentation, and continuous integration. The engine behavior will be implemented in subsequent issues.
