# Contributing to LambdaOpt

Thanks for helping improve LambdaOpt. This project aims to be careful, typed, tested, and safe by default.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,aws,charts]"
pre-commit install
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,aws,charts]"
pre-commit install
```

## Checks

Run the same checks used by CI:

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
python -m build
```

Or use:

```bash
make check
```

## Safety Expectations

- Do not add production Lambda mutation without explicit guardrails.
- Prefer read-only AWS APIs unless a feature is clearly marked unsafe or experimental.
- Never log raw payload contents or secrets.
- Keep AWS-specific code isolated from optimizer logic.
- Add tests for new recommendation behavior and AWS error handling.

## Pull Requests

Please include:

- A short description of the behavior change.
- Tests for new logic.
- Notes about safety implications when touching AWS integrations.
- Documentation updates for new CLI options or workflows.
