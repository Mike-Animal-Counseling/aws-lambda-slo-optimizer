from pytest import MonkeyPatch
from typer.testing import CliRunner

import lambdaopt.cli as cli
from lambdaopt.aws.lambda_client import LambdaFunctionConfiguration
from lambdaopt.benchmark.plan import NO_MUTATION_SAFETY_NOTE, create_benchmark_plan
from lambdaopt.models import LambdaConfig


class FakeLambdaClient:
    def get_function_configuration(self, function_name: str) -> LambdaFunctionConfiguration:
        return LambdaFunctionConfiguration(
            config=LambdaConfig(memory_mb=1024, architecture="arm64", timeout_seconds=30),
            metadata={"runtime": "python3.12", "function_name": function_name},
        )


def test_create_benchmark_plan_includes_current_config_and_safety_note() -> None:
    current = LambdaConfig(memory_mb=3008, architecture="x86_64", timeout_seconds=20)

    plan = create_benchmark_plan(function_name="my-function", current_config=current)

    assert plan.function_name == "my-function"
    assert plan.current_config == current
    assert current in plan.candidate_configs
    assert NO_MUTATION_SAFETY_NOTE in plan.safety_notes


def test_cli_plan_uses_mocked_lambda_client(monkeypatch: MonkeyPatch) -> None:
    def fake_factory(*, profile: str | None = None, region: str | None = None) -> FakeLambdaClient:
        assert profile == "default"
        assert region == "us-east-1"
        return FakeLambdaClient()

    monkeypatch.setattr(cli, "lambda_client_factory", fake_factory)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["plan", "my-function", "--p95", "500", "--region", "us-east-1", "--profile", "default"],
    )

    assert result.exit_code == 0, result.stdout
    assert "Benchmark plan for my-function" in result.stdout
    assert "Current config: 1024MB arm64" in result.stdout
    assert "no production config will be changed" in result.stdout.lower()
    assert "Suggested next command" in result.stdout
