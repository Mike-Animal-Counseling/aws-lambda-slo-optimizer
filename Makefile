.PHONY: install test lint format format-check typecheck build check

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

check: format-check lint typecheck test build
