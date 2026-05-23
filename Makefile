.PHONY: install test lint format typecheck check

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	python -m ruff check .

format:
	python -m ruff format .

typecheck:
	python -m mypy

check: lint typecheck test

