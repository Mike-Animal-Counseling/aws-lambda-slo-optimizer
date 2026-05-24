import json
from pathlib import Path

from lambdaopt.analysis.cost_model import estimate_lambda_cost
from lambdaopt.analysis.latency import calculate_latency_stats
from lambdaopt.models import AnalyzedConfig, LambdaConfig, Recommendation
from lambdaopt.report.json_output import (
    write_benchmark_results_json,
    write_recommendation_json,
)
from lambdaopt.report.markdown import write_markdown_report


def test_report_writers_create_expected_content(tmp_path: Path) -> None:
    config = LambdaConfig(memory_mb=1024, architecture="arm64")
    latency = calculate_latency_stats([100, 120, 140, 160, 180], target_ms=500)
    cost = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=latency.mean_ms,
        monthly_requests=1_000_000,
        architecture="arm64",
    )
    analyzed = AnalyzedConfig(
        config=config,
        latency=latency,
        cost=cost,
        cold_start_rate=0.0,
        slo_passed=True,
    )
    recommendation = Recommendation(
        recommended_config=config,
        reason_summary="1024MB arm64 is the cheapest passing configuration.",
        rejected_reasons={"512mb-x86_64-pc0": "p95 exceeded the target."},
        warnings=[],
        alternatives=[],
        confidence=0.9,
    )

    benchmark_path = write_benchmark_results_json([analyzed], tmp_path)
    recommendation_path = write_recommendation_json(recommendation, tmp_path)
    markdown_path = write_markdown_report(
        analyzed_configs=[analyzed],
        recommendation=recommendation,
        target_p95_ms=500,
        monthly_requests=1_000_000,
        output_dir=tmp_path,
    )

    benchmark_payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    recommendation_payload = json.loads(recommendation_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert benchmark_payload["results"][0]["config"]["memory_mb"] == 1024
    assert recommendation_payload["recommended_config"]["architecture"] == "arm64"
    assert "# LambdaOpt Optimization Report" in markdown
    assert "## SLO Risk Assessment" in markdown
    assert "p95 latency target: 500 ms" in markdown
    assert "1024 MB" in markdown
    assert "512mb-x86_64-pc0" in markdown
