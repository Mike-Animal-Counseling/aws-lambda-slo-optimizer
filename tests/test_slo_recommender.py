from typing import Literal

from lambdaopt.models import AnalyzedConfig, CostEstimate, LambdaConfig, LatencyStats
from lambdaopt.recommend.architecture_recommender import ARM64_COMPATIBILITY_WARNING
from lambdaopt.recommend.slo_recommender import recommend_cheapest_slo_config


def _analyzed_config(
    *,
    memory_mb: int,
    architecture: Literal["x86_64", "arm64"] = "arm64",
    p95_ms: float,
    total_cost_usd: float,
    sample_count: int = 100,
    errors: int = 0,
) -> AnalyzedConfig:
    return AnalyzedConfig(
        config=LambdaConfig(memory_mb=memory_mb, architecture=architecture),
        latency=LatencyStats(
            mean_ms=p95_ms * 0.75,
            p50_ms=p95_ms * 0.65,
            p95_ms=p95_ms,
            p99_ms=p95_ms * 1.1,
            min_ms=p95_ms * 0.4,
            max_ms=p95_ms * 1.2,
            stddev_ms=12,
            sample_count=sample_count,
            slo_violation_rate=0.02,
        ),
        cost=CostEstimate(
            monthly_requests=1_000_000,
            request_cost_usd=0.20,
            compute_cost_usd=max(0.0, total_cost_usd - 0.20),
            provisioned_concurrency_cost_usd=0.0,
            total_cost_usd=total_cost_usd,
            cost_per_million_requests_usd=total_cost_usd,
        ),
        cold_start_rate=0.01,
        slo_passed=p95_ms <= 250,
        errors=errors,
    )


def test_recommender_picks_cheapest_passing_config() -> None:
    failing = _analyzed_config(
        memory_mb=512,
        architecture="x86_64",
        p95_ms=320,
        total_cost_usd=4,
    )
    cheapest_passing = _analyzed_config(memory_mb=1024, p95_ms=220, total_cost_usd=8)
    faster_expensive = _analyzed_config(memory_mb=1536, p95_ms=180, total_cost_usd=12)

    recommendation = recommend_cheapest_slo_config(
        [failing, cheapest_passing, faster_expensive],
        target_p95_ms=250,
    )

    assert recommendation.recommended_config.memory_mb == 1024
    assert recommendation.confidence == 0.9
    assert "512MB x86_64 rejected because p95 320ms exceeds target 250ms" in (
        recommendation.rejected_reasons["512mb-x86_64-pc0"]
    )
    assert "costs 50% more" in recommendation.rejected_reasons["1536mb-arm64-pc0"]


def test_recommender_handles_no_passing_config_case() -> None:
    high_violation = _analyzed_config(memory_mb=512, p95_ms=400, total_cost_usd=4)
    closest = _analyzed_config(memory_mb=1024, p95_ms=275, total_cost_usd=8)
    worse = _analyzed_config(memory_mb=1536, p95_ms=300, total_cost_usd=12)

    recommendation = recommend_cheapest_slo_config(
        [high_violation, closest, worse],
        target_p95_ms=250,
    )

    assert recommendation.recommended_config.memory_mb == 1024
    assert recommendation.confidence == 0.25
    assert recommendation.warnings == [
        "No configuration satisfied the p95 SLO without errors; recommending the closest option."
    ]


def test_recommender_rejects_erroring_config_even_if_latency_passes() -> None:
    erroring = _analyzed_config(memory_mb=512, p95_ms=180, total_cost_usd=4, errors=2)
    valid = _analyzed_config(memory_mb=1024, p95_ms=220, total_cost_usd=8)

    recommendation = recommend_cheapest_slo_config([erroring, valid], target_p95_ms=250)

    assert recommendation.recommended_config.memory_mb == 1024
    assert "recorded 2 errors" in recommendation.rejected_reasons["512mb-arm64-pc0"]


def test_recommender_adds_arm64_reason_and_warning_when_selected() -> None:
    x86 = _analyzed_config(
        memory_mb=1024,
        architecture="x86_64",
        p95_ms=220,
        total_cost_usd=10,
    )
    arm64 = _analyzed_config(
        memory_mb=1024,
        architecture="arm64",
        p95_ms=225,
        total_cost_usd=8,
    )

    recommendation = recommend_cheapest_slo_config([x86, arm64], target_p95_ms=250)

    assert recommendation.recommended_config.architecture == "arm64"
    assert "arm64 satisfies the SLO" in recommendation.reason_summary
    assert ARM64_COMPATIBILITY_WARNING in recommendation.warnings
