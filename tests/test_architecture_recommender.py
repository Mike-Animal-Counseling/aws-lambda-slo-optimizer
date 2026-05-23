from typing import Literal

from lambdaopt.models import AnalyzedConfig, CostEstimate, LambdaConfig, LatencyStats
from lambdaopt.recommend.architecture_recommender import (
    ARM64_COMPATIBILITY_WARNING,
    compare_architecture_pair,
)


def test_arm64_cheaper_and_passes_slo_recommends_arm64() -> None:
    comparison = compare_architecture_pair(
        [
            _analyzed_config("x86_64", p95_ms=240, cost=10),
            _analyzed_config("arm64", p95_ms=230, cost=8),
        ],
        memory_mb=1024,
        target_p95_ms=250,
    )

    assert comparison.status == "clearly_better"
    assert comparison.latency_difference_ms == -10
    assert comparison.cost_difference_usd == -2
    assert ARM64_COMPATIBILITY_WARNING in comparison.warnings


def test_arm64_cheaper_but_fails_slo_is_risky() -> None:
    comparison = compare_architecture_pair(
        [
            _analyzed_config("x86_64", p95_ms=240, cost=10),
            _analyzed_config("arm64", p95_ms=280, cost=8),
        ],
        memory_mb=1024,
        target_p95_ms=250,
    )

    assert comparison.status == "risky_due_to_slower_latency"
    assert "does not safely satisfy the SLO" in comparison.reasoning


def test_missing_x86_pair_is_unknown() -> None:
    comparison = compare_architecture_pair(
        [_analyzed_config("arm64", p95_ms=230, cost=8)],
        memory_mb=1024,
        target_p95_ms=250,
    )

    assert comparison.status == "unknown_due_to_missing_comparison_data"
    assert comparison.x86_p95_ms is None
    assert ARM64_COMPATIBILITY_WARNING in comparison.warnings


def test_arm64_cheaper_but_slower_within_slo() -> None:
    comparison = compare_architecture_pair(
        [
            _analyzed_config("x86_64", p95_ms=200, cost=10),
            _analyzed_config("arm64", p95_ms=230, cost=8),
        ],
        memory_mb=1024,
        target_p95_ms=250,
    )

    assert comparison.status == "cheaper_but_slower_within_slo"
    assert "lower cost and satisfies the SLO" in comparison.reasoning


def _analyzed_config(
    architecture: Literal["x86_64", "arm64"],
    *,
    p95_ms: float,
    cost: float,
) -> AnalyzedConfig:
    return AnalyzedConfig(
        config=LambdaConfig(memory_mb=1024, architecture=architecture),
        latency=LatencyStats(
            mean_ms=p95_ms * 0.8,
            p50_ms=p95_ms * 0.7,
            p95_ms=p95_ms,
            p99_ms=p95_ms * 1.1,
            min_ms=p95_ms * 0.5,
            max_ms=p95_ms * 1.2,
            stddev_ms=10,
            sample_count=100,
            slo_violation_rate=0,
        ),
        cost=CostEstimate(
            monthly_requests=1_000_000,
            request_cost_usd=0.20,
            compute_cost_usd=max(0.0, cost - 0.20),
            provisioned_concurrency_cost_usd=0,
            total_cost_usd=cost,
            cost_per_million_requests_usd=cost,
        ),
        cold_start_rate=0,
        slo_passed=p95_ms <= 250,
    )
