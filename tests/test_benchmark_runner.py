from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

import lambdaopt.cli as cli
from lambdaopt.aws.lambda_client import LambdaFunctionConfiguration
from lambdaopt.benchmark.invoker import InvocationSample
from lambdaopt.benchmark.runner import run_current_config_benchmark
from lambdaopt.models import BenchmarkResult, LambdaConfig


class FakeRunnerClient:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(
        self,
        *,
        FunctionName: str,
        InvocationType: str,
        Payload: bytes,
    ) -> dict[str, Any]:
        self.calls += 1
        return {"StatusCode": 200, "Payload": b"{}"}


def test_runner_collects_latency_samples_and_counts_errors(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")
    samples = [
        InvocationSample(
            latency_ms=100,
            status_code=200,
            function_error=None,
            payload_response_size_bytes=2,
            attempt_count=1,
        ),
        InvocationSample(
            latency_ms=250,
            status_code=200,
            function_error="Unhandled",
            payload_response_size_bytes=20,
            attempt_count=1,
        ),
    ]

    def fake_invoke(**kwargs: object) -> InvocationSample:
        return samples.pop(0)

    monkeypatch.setattr("lambdaopt.benchmark.runner.invoke_lambda_safely", fake_invoke)

    result = run_current_config_benchmark(
        client=FakeRunnerClient(),
        function_name="my-function",
        config=LambdaConfig(memory_mb=1024, architecture="arm64", timeout_seconds=30),
        payload_path=payload_path,
        trials=2,
        runtime="python3.12",
        region="us-east-1",
    )

    assert result.raw_latencies_ms == [100, 250]
    assert result.errors == 1
    assert result.metadata["function_name"] == "my-function"
    assert result.metadata["measured_by"] == "client_observed_latency"


class FakeLambdaClient:
    def __init__(self) -> None:
        self._client = FakeRunnerClient()

    def get_function_configuration(self, function_name: str) -> LambdaFunctionConfiguration:
        return LambdaFunctionConfiguration(
            config=LambdaConfig(memory_mb=1024, architecture="arm64", timeout_seconds=30),
            metadata={"runtime": "python3.12", "function_name": function_name},
        )


def test_cli_bench_writes_report_with_mocked_runner(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "bench"

    def fake_factory(*, profile: str | None = None, region: str | None = None) -> FakeLambdaClient:
        assert profile is None
        assert region == "us-east-1"
        return FakeLambdaClient()

    def fake_runner(**kwargs: object) -> BenchmarkResult:
        return BenchmarkResult(
            config=LambdaConfig(memory_mb=1024, architecture="arm64", timeout_seconds=30),
            raw_latencies_ms=[100, 125, 150, 175, 200],
            errors=0,
            metadata={
                "function_name": "my-function",
                "runtime": "python3.12",
                "region": "us-east-1",
                "measured_by": "client_observed_latency",
            },
        )

    monkeypatch.setattr(cli, "lambda_client_factory", fake_factory)
    monkeypatch.setattr(cli, "current_config_benchmark_runner", fake_runner)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "bench",
            "my-function",
            "--trials",
            "5",
            "--payload",
            str(payload_path),
            "--region",
            "us-east-1",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "benchmark_results.json").exists()
    assert (output_dir / "recommended_config.json").exists()
    report = (output_dir / "optimization_report.md").read_text(encoding="utf-8")
    assert "Benchmarked current deployed config only" in result.stdout
    assert "Client-observed latency" in report
