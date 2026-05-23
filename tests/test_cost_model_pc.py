from lambdaopt.analysis.cost_model import estimate_lambda_cost


def test_cost_model_includes_pc_capacity_cost() -> None:
    without_pc = estimate_lambda_cost(
        memory_mb=1024,
        architecture="x86_64",
        avg_duration_ms=100,
        monthly_requests=1_000_000,
    )
    with_pc = estimate_lambda_cost(
        memory_mb=1024,
        architecture="x86_64",
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        provisioned_concurrency=2,
        provisioned_concurrency_hours=100,
    )

    assert with_pc.provisioned_concurrency_cost_usd > 0
    assert with_pc.total_cost_usd > without_pc.total_cost_usd


def test_pc_capacity_cost_scales_with_hours_and_pc_value() -> None:
    low = estimate_lambda_cost(
        memory_mb=1024,
        architecture="arm64",
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        provisioned_concurrency=1,
        provisioned_concurrency_hours=10,
    )
    high = estimate_lambda_cost(
        memory_mb=1024,
        architecture="arm64",
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        provisioned_concurrency=2,
        provisioned_concurrency_hours=20,
    )

    assert high.provisioned_concurrency_cost_usd == low.provisioned_concurrency_cost_usd * 4
