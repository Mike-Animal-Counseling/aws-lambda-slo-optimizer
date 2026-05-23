"""Local analysis helpers for latency, cost, and Pareto evaluation."""

from lambdaopt.analysis.cost_model import estimate_lambda_cost
from lambdaopt.analysis.latency import calculate_latency_stats
from lambdaopt.analysis.pareto import mark_pareto_frontier

__all__ = [
    "calculate_latency_stats",
    "estimate_lambda_cost",
    "mark_pareto_frontier",
]
