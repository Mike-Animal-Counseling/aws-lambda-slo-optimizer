from lambdaopt.analysis.pareto import mark_pareto_frontier
from lambdaopt.models import AnalyzedConfig, CostEstimate, LambdaConfig, LatencyStats


def _analyzed_config(memory_mb: int, p95_ms: float, total_cost_usd: float) -> AnalyzedConfig:
    return AnalyzedConfig(
        config=LambdaConfig(memory_mb=memory_mb, architecture="arm64"),
        latency=LatencyStats(
            mean_ms=p95_ms * 0.8,
            p50_ms=p95_ms * 0.7,
            p95_ms=p95_ms,
            p99_ms=p95_ms * 1.1,
            min_ms=p95_ms * 0.5,
            max_ms=p95_ms * 1.2,
            stddev_ms=10,
            sample_count=100,
            slo_violation_rate=0.0,
        ),
        cost=CostEstimate(
            monthly_requests=1_000_000,
            request_cost_usd=0.20,
            compute_cost_usd=max(0.0, total_cost_usd - 0.20),
            provisioned_concurrency_cost_usd=0.0,
            total_cost_usd=total_cost_usd,
            cost_per_million_requests_usd=total_cost_usd,
        ),
        cold_start_rate=0.0,
        slo_passed=True,
    )


def test_mark_pareto_frontier_marks_dominated_configs() -> None:
    cheap_slow = _analyzed_config(memory_mb=512, p95_ms=260, total_cost_usd=5)
    balanced = _analyzed_config(memory_mb=1024, p95_ms=180, total_cost_usd=8)
    dominated = _analyzed_config(memory_mb=1536, p95_ms=200, total_cost_usd=10)
    fast_expensive = _analyzed_config(memory_mb=2048, p95_ms=120, total_cost_usd=14)

    marked = mark_pareto_frontier([cheap_slow, balanced, dominated, fast_expensive])

    dominated_by_memory = {config.config.memory_mb: config.dominated for config in marked}
    assert dominated_by_memory == {
        512: False,
        1024: False,
        1536: True,
        2048: False,
    }
