from lambdaopt.analysis.cold_start import (
    analyze_cold_starts_from_messages,
    parse_report_log_line,
)

REPORT_WITH_INIT = (
    "REPORT RequestId: abc\tDuration: 100.00 ms\tBilled Duration: 101 ms\t"
    "Memory Size: 1024 MB\tMax Memory Used: 128 MB\tInit Duration: 250.50 ms"
)
REPORT_WITHOUT_INIT = (
    "REPORT RequestId: def\tDuration: 80.25 ms\tBilled Duration: 81 ms\t"
    "Memory Size: 1024 MB\tMax Memory Used: 130 MB"
)


def test_parse_report_line_with_init_duration() -> None:
    record = parse_report_log_line(REPORT_WITH_INIT)

    assert record is not None
    assert record.duration_ms == 100.0
    assert record.billed_duration_ms == 101
    assert record.memory_size_mb == 1024
    assert record.max_memory_used_mb == 128
    assert record.init_duration_ms == 250.5


def test_parse_report_line_without_init_duration() -> None:
    record = parse_report_log_line(REPORT_WITHOUT_INIT)

    assert record is not None
    assert record.init_duration_ms is None
    assert record.duration_ms == 80.25


def test_cold_start_rate_and_init_percentiles() -> None:
    analysis = analyze_cold_starts_from_messages(
        [REPORT_WITH_INIT, REPORT_WITHOUT_INIT, REPORT_WITH_INIT],
        observed_p95_ms=300,
        observed_p99_ms=900,
    )

    assert analysis.total_reports == 3
    assert analysis.cold_start_count == 2
    assert analysis.cold_start_rate == 2 / 3
    assert analysis.avg_init_duration_ms == 250.5
    assert analysis.p95_init_duration_ms == 250.5
    assert analysis.cold_start_contribution_signal == "likely_cold_start_driven"


def test_low_cold_start_rate_with_high_p95_is_execution_driven() -> None:
    messages = [REPORT_WITHOUT_INIT for _ in range(20)] + [REPORT_WITH_INIT]

    analysis = analyze_cold_starts_from_messages(
        messages,
        observed_p95_ms=700,
        observed_p99_ms=800,
    )

    assert analysis.cold_start_rate < 0.05
    assert analysis.cold_start_contribution_signal == "likely_execution_performance_driven"
    assert "memory and architecture" in analysis.recommendations[0]


def test_missing_logs_returns_unknown_with_warning() -> None:
    analysis = analyze_cold_starts_from_messages([])

    assert analysis.total_reports == 0
    assert analysis.cold_start_contribution_signal == "unknown"
    assert analysis.warnings
