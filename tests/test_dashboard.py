import json
from pathlib import Path

import pytest

import lambdaopt.dashboard.app as dashboard_app
from lambdaopt.dashboard.app import load_dashboard_data
from lambdaopt.exceptions import LambdaOptConfigError


def test_dashboard_module_imports_without_streamlit() -> None:
    assert dashboard_app.BENCHMARK_RESULTS_FILE == "benchmark_results.json"


def test_load_dashboard_data_reads_report_files(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "benchmark_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "config": {"memory_mb": 1024, "architecture": "arm64"},
                        "latency": {"p95_ms": 150.0},
                        "cost": {"total_cost_usd": 2.0},
                        "dominated": False,
                        "cold_start_rate": 0.01,
                        "slo_passed": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "recommended_config.json").write_text(
        json.dumps(
            {
                "recommended_config": {"memory_mb": 1024, "architecture": "arm64"},
                "reason_summary": "Cheapest passing config.",
                "confidence": 0.9,
            }
        ),
        encoding="utf-8",
    )

    data = load_dashboard_data(report_dir)

    assert data.report_dir == report_dir
    assert data.benchmark_results[0]["config"]["memory_mb"] == 1024
    assert data.recommendation["recommended_config"]["architecture"] == "arm64"
    assert data.cloudwatch_analysis is None


def test_load_dashboard_data_rejects_missing_files(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()

    with pytest.raises(LambdaOptConfigError):
        load_dashboard_data(report_dir)
