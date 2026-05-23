from typer.testing import CliRunner

import lambdaopt
from lambdaopt.cli import app
from lambdaopt.models import LambdaCandidateConfig, LatencyPercentile, LatencySLO


def test_package_imports() -> None:
    assert lambdaopt.__version__ == "0.1.0"


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
