import pytest

from lambdaopt.analysis.latency import calculate_latency_stats
from lambdaopt.exceptions import LambdaOptValidationError


def test_percentiles_use_nearest_rank_values() -> None:
    stats = calculate_latency_stats([10, 20, 30, 40, 50], target_ms=100)

    assert stats.mean_ms == 30
    assert stats.p50_ms == 30
    assert stats.p95_ms == 50
    assert stats.p99_ms == 50
    assert stats.min_ms == 10
    assert stats.max_ms == 50
    assert stats.sample_count == 5


def test_slo_violation_rate_counts_samples_above_target() -> None:
    stats = calculate_latency_stats([100, 200, 300, 400], target_ms=250)

    assert stats.slo_violation_rate == 0.5


def test_single_sample_latency_stats_are_valid() -> None:
    stats = calculate_latency_stats([123.4], target_ms=200)

    assert stats.mean_ms == 123.4
    assert stats.p50_ms == 123.4
    assert stats.p95_ms == 123.4
    assert stats.p99_ms == 123.4
    assert stats.stddev_ms == 0


def test_empty_latency_input_fails() -> None:
    with pytest.raises(LambdaOptValidationError):
        calculate_latency_stats([], target_ms=250)
