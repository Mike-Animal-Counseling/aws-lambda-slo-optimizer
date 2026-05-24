from lambdaopt.analysis.risk import assess_config_risk
from lambdaopt.models import AnalyzedConfig, CostEstimate, LambdaConfig, LatencyStats


def test_low_risk_config_gets_high_confidence() -> None:
    risk = assess_config_risk(_config(p95_ms=350, p99_ms=430), target_p95_ms=500)

    assert risk.level == "low"
    assert risk.score == 0
    assert risk.confidence == 0.9
    assert "acceptable" in risk.reasons[0]


def test_near_slo_and_low_samples_raise_medium_risk() -> None:
    risk = assess_config_risk(
        _config(p95_ms=480, p99_ms=610, sample_count=20),
        target_p95_ms=500,
    )

    assert risk.level == "medium"
    assert risk.confidence == 0.4
    assert any("close to target" in reason for reason in risk.reasons)
    assert any("Only 20 latency samples" in reason for reason in risk.reasons)


def test_errors_and_slo_failure_raise_high_risk() -> None:
    risk = assess_config_risk(
        _config(p95_ms=650, p99_ms=900, errors=2, cold_start_rate=0.08),
        target_p95_ms=500,
    )

    assert risk.level == "high"
    assert risk.score == 100
    assert any("benchmark errors" in reason for reason in risk.reasons)
    assert any("Cold start rate" in reason for reason in risk.reasons)


def _config(
    *,
    p95_ms: float,
    p99_ms: float,
    sample_count: int = 100,
    errors: int = 0,
    cold_start_rate: float = 0.0,
) -> AnalyzedConfig:
    return AnalyzedConfig(
        config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        latency=LatencyStats(
            mean_ms=p95_ms * 0.7,
            p50_ms=p95_ms * 0.6,
            p95_ms=p95_ms,
            p99_ms=p99_ms,
            min_ms=p95_ms * 0.4,
            max_ms=p99_ms,
            stddev_ms=10,
            sample_count=sample_count,
            slo_violation_rate=0.01,
        ),
        cost=CostEstimate(
            monthly_requests=1_000_000,
            request_cost_usd=0.20,
            compute_cost_usd=3.80,
            provisioned_concurrency_cost_usd=0.0,
            total_cost_usd=4.0,
            cost_per_million_requests_usd=4.0,
        ),
        cold_start_rate=cold_start_rate,
        slo_passed=p95_ms <= 500,
        errors=errors,
    )
