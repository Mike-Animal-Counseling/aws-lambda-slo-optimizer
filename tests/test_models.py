from pathlib import Path

import pytest
from pydantic import ValidationError

from lambdaopt.config import load_benchmark_results
from lambdaopt.models import (
    AnalyzedConfig,
    BenchmarkResult,
    CostEstimate,
    LambdaConfig,
    LatencyStats,
    Recommendation,
)


def test_valid_models_parse_successfully() -> None:
    config = LambdaConfig(
        memory_mb=1024,
        architecture="arm64",
        timeout_seconds=10,
        provisioned_concurrency=0,
    )
    latency = LatencyStats(
        mean_ms=130.0,
        p50_ms=125.0,
        p95_ms=190.0,
        p99_ms=210.0,
        min_ms=95.0,
        max_ms=220.0,
        stddev_ms=18.5,
        sample_count=100,
        slo_violation_rate=0.01,
    )
    benchmark = BenchmarkResult(config=config, raw_latencies_ms=[101.2, 118.4, 135.9])
    cost = CostEstimate(
        monthly_requests=1_000_000,
        request_cost_usd=0.20,
        compute_cost_usd=8.42,
        provisioned_concurrency_cost_usd=0.0,
        total_cost_usd=8.62,
        cost_per_million_requests_usd=8.62,
    )
    analyzed = AnalyzedConfig(
        config=config,
        latency=latency,
        cost=cost,
        cold_start_rate=0.02,
        slo_passed=True,
    )
    recommendation = Recommendation(
        recommended_config=config,
        reason_summary="Cheapest configuration that satisfies the p95 SLO.",
        rejected_reasons={"512-x86_64": "p95 latency exceeded the SLO."},
        warnings=[],
        alternatives=[analyzed],
        confidence=0.9,
    )

    assert benchmark.config == config
    assert analyzed.slo_passed is True
    assert recommendation.recommended_config.memory_mb == 1024


def test_invalid_memory_fails() -> None:
    with pytest.raises(ValidationError):
        LambdaConfig(memory_mb=64, architecture="x86_64")


def test_invalid_architecture_fails() -> None:
    with pytest.raises(ValidationError):
        LambdaConfig.model_validate({"memory_mb": 512, "architecture": "sparc"})


def test_empty_latency_list_fails() -> None:
    with pytest.raises(ValidationError):
        BenchmarkResult(
            config=LambdaConfig(memory_mb=512, architecture="x86_64"),
            raw_latencies_ms=[],
        )


def test_sample_results_json_loads_into_benchmark_results() -> None:
    sample_path = Path(__file__).parent.parent / "examples" / "sample_results.json"

    results = load_benchmark_results(sample_path)

    assert len(results) == 4
    assert all(isinstance(result, BenchmarkResult) for result in results)
    assert [result.config.memory_mb for result in results] == [512, 1024, 1536, 2048]
    assert results[0].metadata["expected_slo_passed"] is False
    assert results[1].config.architecture == "arm64"
