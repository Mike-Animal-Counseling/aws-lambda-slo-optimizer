from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

import lambdaopt.cli as cli
from lambdaopt.benchmark.candidate_runner import (
    CandidateFunctionMappings,
    load_candidate_function_mappings,
    run_candidate_function_benchmarks,
)
from lambdaopt.benchmark.invoker import InvocationSample
from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import BenchmarkResult, LambdaConfig


class FakeInvokeClient:
    def invoke(
        self,
        *,
        FunctionName: str,
        InvocationType: str,
        Payload: bytes,
    ) -> dict[str, Any]:
        return {"StatusCode": 200, "Payload": b"{}"}


class FakeLambdaClient:
    def __init__(self) -> None:
        self._client = FakeInvokeClient()


def test_candidate_mapping_validation_loads_valid_file(tmp_path: Path) -> None:
    mapping_path = tmp_path / "candidates.json"
    mapping_path.write_text(
        """
        {
          "candidates": [
            {
              "function_name": "my-fn-512-x86-test",
              "memory_mb": 512,
              "architecture": "x86_64"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    mappings = load_candidate_function_mappings(mapping_path)

    assert len(mappings.candidates) == 1
    assert mappings.candidates[0].config == LambdaConfig(
        memory_mb=512,
        architecture="x86_64",
    )


def test_candidate_mapping_validation_rejects_invalid_memory(tmp_path: Path) -> None:
    mapping_path = tmp_path / "candidates.json"
    mapping_path.write_text(
        """
        {
          "candidates": [
            {
              "function_name": "bad",
              "memory_mb": 64,
              "architecture": "arm64"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(LambdaOptValidationError):
        load_candidate_function_mappings(mapping_path)


def test_candidate_runner_collects_results_with_mocked_invoker(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")
    mappings = CandidateFunctionMappings.model_validate(
        {
            "candidates": [
                {
                    "function_name": "fn-512",
                    "memory_mb": 512,
                    "architecture": "x86_64",
                },
                {
                    "function_name": "fn-1024",
                    "memory_mb": 1024,
                    "architecture": "arm64",
                },
            ]
        }
    )

    latencies = [200.0, 210.0, 120.0, 130.0]

    def fake_invoke(**kwargs: object) -> InvocationSample:
        return InvocationSample(
            latency_ms=latencies.pop(0),
            status_code=200,
            function_error=None,
            payload_response_size_bytes=2,
            attempt_count=1,
        )

    monkeypatch.setattr("lambdaopt.benchmark.candidate_runner.invoke_lambda_safely", fake_invoke)

    results = run_candidate_function_benchmarks(
        client=FakeInvokeClient(),
        mappings=mappings,
        payload_path=payload_path,
        trials=2,
        region="us-east-1",
    )

    assert [result.config.memory_mb for result in results] == [512, 1024]
    assert results[0].raw_latencies_ms == [200.0, 210.0]
    assert results[1].raw_latencies_ms == [120.0, 130.0]
    assert results[0].metadata["candidate_function_name"] == "fn-512"


def test_cli_tune_with_candidates_creates_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    mapping_path = tmp_path / "candidates.json"
    mapping_path.write_text(
        """
        {
          "candidates": [
            {
              "function_name": "fn-512",
              "memory_mb": 512,
              "architecture": "x86_64"
            },
            {
              "function_name": "fn-1024",
              "memory_mb": 1024,
              "architecture": "arm64"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "reports"

    def fake_factory(*, profile: str | None = None, region: str | None = None) -> FakeLambdaClient:
        assert profile is None
        assert region is None
        return FakeLambdaClient()

    def fake_runner(**kwargs: object) -> list[BenchmarkResult]:
        return [
            BenchmarkResult(
                config=LambdaConfig(memory_mb=512, architecture="x86_64"),
                raw_latencies_ms=[400, 420, 440],
                metadata={"candidate_function_name": "fn-512"},
            ),
            BenchmarkResult(
                config=LambdaConfig(memory_mb=1024, architecture="arm64"),
                raw_latencies_ms=[120, 140, 160],
                metadata={"candidate_function_name": "fn-1024"},
            ),
        ]

    monkeypatch.setattr(cli, "lambda_client_factory", fake_factory)
    monkeypatch.setattr(cli, "candidate_function_benchmark_runner", fake_runner)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "tune",
            "--candidates",
            str(mapping_path),
            "--p95",
            "500",
            "--monthly-requests",
            "1000000",
            "--trials",
            "3",
            "--yes",
            "--payload",
            str(payload_path),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "benchmark_results.json").exists()
    assert (output_dir / "recommended_config.json").exists()
    report = (output_dir / "optimization_report.md").read_text(encoding="utf-8")
    assert "separate candidate test functions" in result.stdout
    assert "separate candidate test functions" in report


def test_cli_tune_rejects_input_and_candidates_together(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = Path(__file__).parent.parent / "examples" / "sample_results.json"
    mapping_path = Path(__file__).parent.parent / "examples" / "candidate_functions.json"

    result = runner.invoke(
        cli.app,
        [
            "tune",
            "--input",
            str(input_path),
            "--candidates",
            str(mapping_path),
            "--p95",
            "500",
            "--monthly-requests",
            "1000000",
            "--output",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code != 0
    assert "Use either --input or --candidates" in result.output
