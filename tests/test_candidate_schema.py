from pathlib import Path

import pytest

from lambdaopt.benchmark.candidate_schema import load_candidate_mappings
from lambdaopt.exceptions import LambdaOptValidationError


def test_valid_candidate_file_supports_aliases_and_test_functions(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        """
        {
          "base_function_name": "my-function",
          "notes": "non-production candidates",
          "candidates": [
            {
              "name": "512MB x86 test",
              "function_ref": "my-function:test-512-x86",
              "memory_mb": 512,
              "architecture": "x86_64"
            },
            {
              "name": "1024MB arm function",
              "function_ref": "my-function-1024-arm-test",
              "memory_mb": 1024,
              "architecture": "arm64"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    mappings = load_candidate_mappings(path)

    assert mappings.base_function_name == "my-function"
    assert mappings.candidates[0].source_type == "alias"
    assert mappings.candidates[1].source_type == "test_function"


def test_duplicate_candidate_name_fails(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        """
        {
          "candidates": [
            {
              "name": "duplicate",
              "function_ref": "fn:test-a",
              "memory_mb": 512,
              "architecture": "x86_64"
            },
            {
              "name": "duplicate",
              "function_ref": "fn:test-b",
              "memory_mb": 1024,
              "architecture": "arm64"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(LambdaOptValidationError):
        load_candidate_mappings(path)


def test_invalid_architecture_fails(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        """
        {
          "candidates": [
            {
              "name": "bad arch",
              "function_ref": "fn:test",
              "memory_mb": 512,
              "architecture": "riscv"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(LambdaOptValidationError):
        load_candidate_mappings(path)


def test_production_alias_fails_by_default(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        """
        {
          "candidates": [
            {
              "name": "prod alias",
              "function_ref": "fn:prod",
              "memory_mb": 512,
              "architecture": "x86_64"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(LambdaOptValidationError):
        load_candidate_mappings(path)

    assert load_candidate_mappings(path, allow_production_candidate=True).candidates[0].name
