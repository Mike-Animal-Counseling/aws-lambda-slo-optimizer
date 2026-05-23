from lambdaopt.analysis.cost_model import estimate_lambda_cost


def test_cost_increases_with_memory() -> None:
    low_memory = estimate_lambda_cost(
        memory_mb=512,
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        architecture="x86_64",
    )
    high_memory = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        architecture="x86_64",
    )

    assert high_memory.total_cost_usd > low_memory.total_cost_usd


def test_cost_increases_with_duration() -> None:
    short_duration = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        architecture="x86_64",
    )
    long_duration = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=250,
        monthly_requests=1_000_000,
        architecture="x86_64",
    )

    assert long_duration.total_cost_usd > short_duration.total_cost_usd


def test_arm64_is_cheaper_than_x86_for_same_workload() -> None:
    x86 = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=200,
        monthly_requests=1_000_000,
        architecture="x86_64",
    )
    arm64 = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=200,
        monthly_requests=1_000_000,
        architecture="arm64",
    )

    assert arm64.compute_cost_usd < x86.compute_cost_usd
    assert arm64.total_cost_usd < x86.total_cost_usd


def test_provisioned_concurrency_adds_cost() -> None:
    on_demand = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        architecture="arm64",
    )
    provisioned = estimate_lambda_cost(
        memory_mb=1024,
        avg_duration_ms=100,
        monthly_requests=1_000_000,
        architecture="arm64",
        provisioned_concurrency=1,
        provisioned_concurrency_hours=24,
    )

    assert provisioned.provisioned_concurrency_cost_usd > 0
    assert provisioned.total_cost_usd > on_demand.total_cost_usd
