from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

import lambdaopt.cli as cli
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


def test_tune_candidates_dry_run_plan_does_not_invoke(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    mapping_path = _candidate_file(tmp_path)
    output_dir = tmp_path / "reports"
    invoked = False

    def fake_factory(*, profile: str | None = None, region: str | None = None) -> FakeLambdaClient:
        raise AssertionError("Lambda client should not be created for dry-run-plan")

    def fake_runner(**kwargs: object) -> list[BenchmarkResult]:
        nonlocal invoked
        invoked = True
        return []

    monkeypatch.setattr(cli, "lambda_client_factory", fake_factory)
    monkeypatch.setattr(cli, "candidate_function_benchmark_runner", fake_runner)
    result = CliRunner().invoke(
        cli.app,
        [
            "tune",
            "--candidates",
            str(mapping_path),
            "--p95",
            "500",
            "--trials",
            "50",
            "--output",
            str(output_dir),
            "--dry-run-plan",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Candidate benchmark plan" in result.output
    assert "Estimated measured invocations: 100" in result.output
    assert "no Lambda memory" in result.output
    assert not invoked
    assert not output_dir.exists()


def test_tune_candidates_requires_confirmation_without_yes(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli.app,
        [
            "tune",
            "--candidates",
            str(_candidate_file(tmp_path)),
            "--p95",
            "500",
            "--trials",
            "2",
            "--output",
            str(tmp_path / "reports"),
        ],
        input="n\n",
    )

    assert result.exit_code == 1
    assert "Candidate benchmarking cancelled by user" in result.output


def test_tune_candidates_report_includes_candidate_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    output_dir = tmp_path / "reports"

    def fake_factory(*, profile: str | None = None, region: str | None = None) -> FakeLambdaClient:
        return FakeLambdaClient()

    def fake_runner(**kwargs: object) -> list[BenchmarkResult]:
        return [
            BenchmarkResult(
                config=LambdaConfig(memory_mb=512, architecture="x86_64"),
                raw_latencies_ms=[300, 320, 340],
                metadata={
                    "candidate_name": "512MB x86 test",
                    "candidate_function_ref": "my-function:test-512-x86",
                    "candidate_source": "alias",
                },
            ),
            BenchmarkResult(
                config=LambdaConfig(memory_mb=1024, architecture="arm64"),
                raw_latencies_ms=[120, 140, 160],
                metadata={
                    "candidate_name": "1024MB arm test",
                    "candidate_function_ref": "my-function:test-1024-arm",
                    "candidate_source": "alias",
                },
            ),
        ]

    monkeypatch.setattr(cli, "lambda_client_factory", fake_factory)
    monkeypatch.setattr(cli, "candidate_function_benchmark_runner", fake_runner)

    result = CliRunner().invoke(
        cli.app,
        [
            "tune",
            "--candidates",
            str(_candidate_file(tmp_path)),
            "--p95",
            "500",
            "--trials",
            "2",
            "--output",
            str(output_dir),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    report = (output_dir / "optimization_report.md").read_text(encoding="utf-8")
    assert "512MB x86 test" in report
    assert "my-function:test-512-x86" in report
    assert "alias" in report


def _candidate_file(tmp_path: Path) -> Path:
    path = tmp_path / "candidates.json"
    path.write_text(
        """
        {
          "base_function_name": "my-function",
          "notes": "non-production aliases",
          "candidates": [
            {
              "name": "512MB x86 test",
              "function_ref": "my-function:test-512-x86",
              "memory_mb": 512,
              "architecture": "x86_64"
            },
            {
              "name": "1024MB arm test",
              "function_ref": "my-function:test-1024-arm",
              "memory_mb": 1024,
              "architecture": "arm64"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    return path
