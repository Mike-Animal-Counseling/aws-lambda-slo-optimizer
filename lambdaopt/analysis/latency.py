"""Latency analysis helpers."""

from math import ceil, fsum, sqrt

from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import LatencyStats


def calculate_latency_stats(latencies_ms: list[float], target_ms: float) -> LatencyStats:
    """Calculate deterministic latency statistics for raw duration samples.

    Percentiles use the nearest-rank method, which is stable for small sample
    sizes and intentionally selects an observed latency value.
    """
    if not latencies_ms:
        raise LambdaOptValidationError("latencies_ms must contain at least one sample.")

    if target_ms <= 0:
        raise LambdaOptValidationError("target_ms must be positive.")

    if any(latency < 0 for latency in latencies_ms):
        raise LambdaOptValidationError("latencies_ms cannot contain negative values.")

    sorted_latencies = sorted(latencies_ms)
    sample_count = len(sorted_latencies)
    mean_ms = fsum(sorted_latencies) / sample_count
    variance = fsum((latency - mean_ms) ** 2 for latency in sorted_latencies) / sample_count
    violations = sum(1 for latency in sorted_latencies if latency > target_ms)

    return LatencyStats(
        mean_ms=mean_ms,
        p50_ms=_nearest_rank_percentile(sorted_latencies, 50),
        p95_ms=_nearest_rank_percentile(sorted_latencies, 95),
        p99_ms=_nearest_rank_percentile(sorted_latencies, 99),
        min_ms=sorted_latencies[0],
        max_ms=sorted_latencies[-1],
        stddev_ms=sqrt(variance),
        sample_count=sample_count,
        slo_violation_rate=violations / sample_count,
    )


def _nearest_rank_percentile(sorted_values: list[float], percentile: int) -> float:
    """Return a percentile using the nearest-rank method."""
    rank = ceil((percentile / 100) * len(sorted_values))
    index = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[index]
