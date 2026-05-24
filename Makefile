.PHONY: install test lint format format-check typecheck build security-check check

install:
	python -m pip install -e ".[dev,aws,charts]"

test:
	python -m pytest

lint:
	python -m ruff check .

format:
	python -m ruff format .

format-check:
	python -m ruff format --check .

typecheck:
	python -m mypy

build:
	python -m build

security-check:
	python -m pytest tests/test_security_redaction.py tests/test_no_credentials_in_reports.py tests/test_doctor.py tests/test_iam_generate.py
	python -c "from pathlib import Path; forbidden=['--access-key','--secret-key','--session-token','--aws-access-key-id','--aws-secret-access-key']; text='\n'.join(p.read_text(encoding='utf-8') for p in Path('lambdaopt').rglob('*.py')); found=[item for item in forbidden if item in text]; raise SystemExit('Forbidden direct credential CLI flags: '+', '.join(found) if found else 0)"
	python -c "from pathlib import Path; forbidden=['AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN']; text='\n'.join(p.read_text(encoding='utf-8') for p in Path('.github/workflows').glob('*.yml')); found=[item for item in forbidden if item in text]; raise SystemExit('Forbidden AWS secret references in workflows: '+', '.join(found) if found else 0)"

check: format-check lint typecheck test build
