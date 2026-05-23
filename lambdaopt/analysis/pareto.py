"""Pareto frontier helpers for analyzed Lambda configurations."""

from lambdaopt.models import AnalyzedConfig


def mark_pareto_frontier(configs: list[AnalyzedConfig]) -> list[AnalyzedConfig]:
    """Return configs with ``dominated`` marked from cost and p95 latency."""
    return [
        config.model_copy(update={"dominated": _is_dominated(config, configs)})
        for config in configs
    ]


def _is_dominated(candidate: AnalyzedConfig, configs: list[AnalyzedConfig]) -> bool:
    for other in configs:
        if other is candidate:
            continue

        cost_not_worse = other.cost.total_cost_usd <= candidate.cost.total_cost_usd
        latency_not_worse = other.latency.p95_ms <= candidate.latency.p95_ms
        strictly_better = (
            other.cost.total_cost_usd < candidate.cost.total_cost_usd
            or other.latency.p95_ms < candidate.latency.p95_ms
        )

        if cost_not_worse and latency_not_worse and strictly_better:
            return True

    return False
