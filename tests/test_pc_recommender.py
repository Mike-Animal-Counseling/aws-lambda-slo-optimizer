from lambdaopt.recommend.pc_recommender import recommend_provisioned_concurrency


def test_high_cold_start_p99_case_recommends_pc_test() -> None:
    recommendation = recommend_provisioned_concurrency(
        cold_start_rate=0.12,
        p95_ms=300,
        p99_ms=900,
        target_p95_ms=500,
        target_p99_ms=600,
        current_memory_mb=1024,
        monthly_requests=1_000_000,
        peak_hours_per_month=80,
        architecture="arm64",
        avg_duration_ms=150,
    )

    assert recommendation.recommended_provisioned_concurrency == 1
    assert recommendation.expected_benefit == "high"
    assert recommendation.monthly_cost_impact_usd > 0
    assert "peak windows" in recommendation.reasoning


def test_low_cold_start_case_does_not_recommend_pc() -> None:
    recommendation = recommend_provisioned_concurrency(
        cold_start_rate=0.001,
        p95_ms=550,
        p99_ms=650,
        target_p95_ms=500,
        current_memory_mb=1024,
        monthly_requests=1_000_000,
        peak_hours_per_month=80,
        architecture="arm64",
        avg_duration_ms=200,
    )

    assert recommendation.recommended_provisioned_concurrency == 0
    assert recommendation.expected_benefit == "low"
    assert "not recommended" in recommendation.reasoning


def test_low_traffic_high_pc_cost_warns() -> None:
    recommendation = recommend_provisioned_concurrency(
        cold_start_rate=0.2,
        p95_ms=200,
        p99_ms=900,
        target_p95_ms=500,
        current_memory_mb=2048,
        monthly_requests=10_000,
        peak_hours_per_month=100,
        architecture="x86_64",
        avg_duration_ms=150,
    )

    assert recommendation.recommended_provisioned_concurrency == 1
    assert any("Traffic is low" in warning for warning in recommendation.warnings)
    assert any("Prefer peak-window PC" in warning for warning in recommendation.warnings)


def test_unknown_benefit_when_percentiles_missing() -> None:
    recommendation = recommend_provisioned_concurrency(
        cold_start_rate=0.2,
        p95_ms=None,
        p99_ms=None,
        target_p95_ms=500,
        current_memory_mb=1024,
        monthly_requests=1_000_000,
        peak_hours_per_month=80,
    )

    assert recommendation.recommended_provisioned_concurrency == 0
    assert recommendation.expected_benefit == "unknown"
