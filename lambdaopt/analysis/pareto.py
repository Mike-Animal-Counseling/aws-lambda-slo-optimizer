"""Pareto frontier helpers for analyzed Lambda configurations."""

from lambdaopt.models import AnalyzedConfig


def mark_pareto_frontier(configs: list[AnalyzedConfig]) -> list[AnalyzedConfig]:
    """Return configs with ``dominated`` marked across cost and production SLO signals."""
    return [
        config.model_copy(update={"dominated": _is_dominated(config, configs)})
        for config in configs
    ]


def _is_dominated(candidate: AnalyzedConfig, configs: list[AnalyzedConfig]) -> bool:
    for other in configs:
        if other is candidate:
            continue

        if _dominates(other, candidate):
            return True

    return False


def _dominates(other: AnalyzedConfig, candidate: AnalyzedConfig) -> bool:
    not_worse = (
        other.cost.total_cost_usd <= candidate.cost.total_cost_usd
        and other.latency.p95_ms <= candidate.latency.p95_ms
        and other.latency.p99_ms <= candidate.latency.p99_ms
        and other.errors <= candidate.errors
        and other.cold_start_rate <= candidate.cold_start_rate
    )
    strictly_better = (
        other.cost.total_cost_usd < candidate.cost.total_cost_usd
        or other.latency.p95_ms < candidate.latency.p95_ms
        or other.latency.p99_ms < candidate.latency.p99_ms
        or other.errors < candidate.errors
        or other.cold_start_rate < candidate.cold_start_rate
    )
    return not_worse and strictly_better
