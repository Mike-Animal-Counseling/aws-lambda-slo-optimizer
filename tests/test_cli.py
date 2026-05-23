import json
from pathlib import Path

from typer.testing import CliRunner

from lambdaopt.cli import app


def test_tune_command_exits_zero_and_writes_outputs(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = Path(__file__).parent.parent / "examples" / "sample_results.json"
    output_dir = tmp_path / "sample"

    result = runner.invoke(
        app,
        [
            "tune",
            "--input",
            str(input_path),
            "--p95",
            "500",
            "--monthly-requests",
            "1000000",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "benchmark_results.json").exists()
    assert (output_dir / "recommended_config.json").exists()
    assert (output_dir / "optimization_report.md").exists()

    recommendation = json.loads((output_dir / "recommended_config.json").read_text())
    assert recommendation["recommended_config"]["memory_mb"] == 1024
    assert recommendation["recommended_config"]["architecture"] == "arm64"

    report = (output_dir / "optimization_report.md").read_text(encoding="utf-8")
    assert "p95 latency target: 500 ms" in report
    assert "1024 MB" in report
    assert "arm64" in report
    assert "Recommendation" in result.stdout
