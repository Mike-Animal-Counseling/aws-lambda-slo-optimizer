from typer.testing import CliRunner

import lambdaopt
from lambdaopt.cli import app
from lambdaopt.models import LambdaCandidateConfig, LatencyPercentile, LatencySLO


def test_package_imports() -> None:
    assert lambdaopt.__version__ == "0.2.1"


def test_models_validate_basic_values() -> None:
    slo = LatencySLO(percentile=LatencyPercentile.P95, threshold_ms=250)
    candidate = LambdaCandidateConfig(memory_mb=512, architecture="x86_64")

    assert slo.percentile == LatencyPercentile.P95
    assert candidate.memory_mb == 512


def test_version_command() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["version", "--plain"])

    assert result.exit_code == 0
    assert result.stdout.strip() == lambdaopt.__version__


def test_quickstart_command_shows_safe_first_steps() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["quickstart", "my-fn", "--p95", "500", "--region", "us-east-1"])

    assert result.exit_code == 0
    assert "lambdaopt start" in result.stdout
    assert "lambdaopt doctor" in result.stdout
    assert "lambdaopt tune --input" in result.stdout
    assert "lambdaopt plan my-fn --p95 500 --region us-east-1" in result.stdout
    assert "does not mutate production" in result.stdout
