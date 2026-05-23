"""Cold start analysis from Lambda REPORT log lines."""

import re
from math import ceil

from pydantic import BaseModel, ConfigDict, Field

REPORT_DURATION_RE = re.compile(r"Duration:\s+(?P<value>[\d.]+)\s+ms")
BILLED_DURATION_RE = re.compile(r"Billed Duration:\s+(?P<value>\d+)\s+ms")
MEMORY_SIZE_RE = re.compile(r"Memory Size:\s+(?P<value>\d+)\s+MB")
MAX_MEMORY_USED_RE = re.compile(r"Max Memory Used:\s+(?P<value>\d+)\s+MB")
INIT_DURATION_RE = re.compile(r"Init Duration:\s+(?P<value>[\d.]+)\s+ms")
HIGH_COLD_START_RATE = 0.05
P99_P95_GAP_RATIO = 1.8


class ReportLogRecord(BaseModel):
    """Parsed fields from one Lambda REPORT log line."""

    model_config = ConfigDict(frozen=True)

    duration_ms: float
    billed_duration_ms: int
    memory_size_mb: int
    max_memory_used_mb: int
    init_duration_ms: float | None = None


class ColdStartAnalysis(BaseModel):
    """Cold-start summary and diagnosis from REPORT logs."""

    model_config = ConfigDict(frozen=True)

    total_reports: int
    cold_start_count: int
    cold_start_rate: float = Field(ge=0)
    avg_init_duration_ms: float | None = None
    p95_init_duration_ms: float | None = None
    p99_init_duration_ms: float | None = None
    cold_start_contribution_signal: str
    diagnosis: str
    recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def parse_report_log_line(message: str) -> ReportLogRecord | None:
    """Parse a Lambda REPORT log line, tolerating field order and Init absence."""
    if "REPORT" not in message:
        return None

    duration = _float_match(REPORT_DURATION_RE, message)
    billed_duration = _int_match(BILLED_DURATION_RE, message)
    memory_size = _int_match(MEMORY_SIZE_RE, message)
    max_memory_used = _int_match(MAX_MEMORY_USED_RE, message)
    if (
        duration is None
        or billed_duration is None
        or memory_size is None
        or max_memory_used is None
    ):
        return None

    return ReportLogRecord(
        duration_ms=duration,
        billed_duration_ms=billed_duration,
        memory_size_mb=memory_size,
        max_memory_used_mb=max_memory_used,
        init_duration_ms=_float_match(INIT_DURATION_RE, message),
    )


def analyze_cold_starts_from_messages(
    messages: list[str],
    *,
    observed_p95_ms: float | None = None,
    observed_p99_ms: float | None = None,
) -> ColdStartAnalysis:
    """Analyze cold starts from raw Lambda REPORT log messages."""
    records = [
        record
        for message in messages
        if (record := parse_report_log_line(message)) is not None
    ]
    if not records:
        return ColdStartAnalysis(
            total_reports=0,
            cold_start_count=0,
            cold_start_rate=0.0,
            cold_start_contribution_signal="unknown",
            diagnosis="Cold-start impact is unknown because no parseable REPORT logs were found.",
            recommendations=["Verify CloudWatch Logs permissions and log retention."],
            warnings=["No parseable Lambda REPORT logs were available."],
        )

    init_durations = [
        record.init_duration_ms for record in records if record.init_duration_ms is not None
    ]
    cold_start_count = len(init_durations)
    cold_start_rate = cold_start_count / len(records)
    signal, diagnosis, recommendations = _diagnose(
        cold_start_rate=cold_start_rate,
        observed_p95_ms=observed_p95_ms,
        observed_p99_ms=observed_p99_ms,
    )
    warnings = []
    if len(records) != len(messages):
        warnings.append(
            "Some log messages were not parseable REPORT lines; cold-start rate is approximate."
        )
    if not init_durations:
        warnings.append(
            "No Init Duration fields were found; exact cold-start rate cannot be claimed."
        )

    return ColdStartAnalysis(
        total_reports=len(records),
        cold_start_count=cold_start_count,
        cold_start_rate=cold_start_rate,
        avg_init_duration_ms=_average(init_durations),
        p95_init_duration_ms=_nearest_rank_percentile(init_durations, 95),
        p99_init_duration_ms=_nearest_rank_percentile(init_durations, 99),
        cold_start_contribution_signal=signal,
        diagnosis=diagnosis,
        recommendations=recommendations,
        warnings=warnings,
    )


def _diagnose(
    *,
    cold_start_rate: float,
    observed_p95_ms: float | None,
    observed_p99_ms: float | None,
) -> tuple[str, str, list[str]]:
    high_tail_gap = (
        observed_p95_ms is not None
        and observed_p99_ms is not None
        and observed_p95_ms > 0
        and observed_p99_ms >= observed_p95_ms * P99_P95_GAP_RATIO
    )
    if cold_start_rate >= HIGH_COLD_START_RATE and high_tail_gap:
        return (
            "likely_cold_start_driven",
            "High cold-start rate plus a large p99/p95 gap suggests "
            "cold-start-driven tail latency.",
            ["Consider provisioned concurrency if p99 risk appears cold-start-driven."],
        )
    if cold_start_rate < HIGH_COLD_START_RATE and observed_p95_ms is not None:
        return (
            "likely_execution_performance_driven",
            "Cold-start rate is low; elevated p95 is more likely execution-performance-driven.",
            ["Test memory and architecture changes before considering provisioned concurrency."],
        )
    return (
        "inconclusive",
        "Cold-start contribution is inconclusive from available logs and metrics.",
        ["Run benchmark and inspect CloudWatch Logs around p99 latency spikes."],
    )


def _float_match(pattern: re.Pattern[str], message: str) -> float | None:
    match = pattern.search(message)
    return float(match.group("value")) if match else None


def _int_match(pattern: re.Pattern[str], message: str) -> int | None:
    match = pattern.search(message)
    return int(match.group("value")) if match else None


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _nearest_rank_percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    rank = ceil((percentile / 100) * len(sorted_values))
    return sorted_values[min(max(rank - 1, 0), len(sorted_values) - 1)]
