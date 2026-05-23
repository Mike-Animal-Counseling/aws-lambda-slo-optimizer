from pathlib import Path

import pytest
from typer.testing import CliRunner

from lambdaopt.cli import app
from lambdaopt.config import LambdaOptConfig, load_config
from lambdaopt.exceptions import LambdaOptConfigError


def test_load_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "lambdaopt.yaml"
    config_path.write_text(
        """
        default_region: us-east-1
        default_profile: dev
        default_monthly_requests: 2000000
        default_memory_sizes: [512, 1024]
        default_architectures: [arm64]
        report_output_dir: custom-reports
        cost_rates:
          request_cost_per_million_usd: 0.25
        safety:
          allow_production_mutation: false
          require_confirmation: true
        """,
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.default_region == "us-east-1"
    assert config.default_profile == "dev"
    assert config.default_monthly_requests == 2_000_000
    assert config.default_memory_sizes == [512, 1024]
    assert config.default_architectures == ["arm64"]
    assert config.report_output_dir == Path("custom-reports")
    assert config.cost_rates.request_cost_per_million_usd == 0.25
    assert not config.safety.allow_production_mutation
    assert config.safety.require_confirmation


def test_load_config_uses_defaults_when_default_file_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert isinstance(config, LambdaOptConfig)
    assert config.default_region is None
    assert not config.safety.allow_production_mutation


def test_load_config_rejects_invalid_values(tmp_path: Path) -> None:
    config_path = tmp_path / "lambdaopt.yaml"
    config_path.write_text("default_memory_sizes: [64]\n", encoding="utf-8")

    with pytest.raises(LambdaOptConfigError):
        load_config(config_path)


def test_cli_known_error_display_is_concise(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = Path(__file__).parent.parent / "examples" / "sample_results.json"
    candidates_path = Path(__file__).parent.parent / "examples" / "candidate_functions.json"

    result = runner.invoke(
        app,
        [
            "tune",
            "--input",
            str(input_path),
            "--candidates",
            str(candidates_path),
            "--p95",
            "500",
            "--monthly-requests",
            "1000000",
            "--output",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 1
    assert "Error: Use either --input or --candidates" in result.output
    assert "Traceback" not in result.output


def test_cli_debug_mode_shows_traceback_for_known_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = Path(__file__).parent.parent / "examples" / "sample_results.json"
    candidates_path = Path(__file__).parent.parent / "examples" / "candidate_functions.json"

    result = runner.invoke(
        app,
        [
            "--debug",
            "tune",
            "--input",
            str(input_path),
            "--candidates",
            str(candidates_path),
            "--p95",
            "500",
            "--monthly-requests",
            "1000000",
            "--output",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 1
    assert "Traceback" in result.output
    assert "Use either --input or --candidates" in result.output
