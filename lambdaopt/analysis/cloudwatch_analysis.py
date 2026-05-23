"""Analyze CloudWatch Lambda metrics for production SLO health."""

from pydantic import BaseModel, ConfigDict, Field

from lambdaopt.analysis.cold_start import ColdStartAnalysis
from lambdaopt.analysis.cost_model import estimate_lambda_cost
from lambdaopt.aws.cloudwatch_client import LambdaCloudWatchMetrics, MetricSeries
from lambdaopt.models import CostEstimate, LambdaConfig
from lambdaopt.recommend.pc_recommender import (
    ProvisionedConcurrencyRecommendation,
    recommend_provisioned_concurrency,
)

NEAR_SLO_RATIO = 0.9
FAR_BELOW_SLO_RATIO = 0.5
P99_TO_P95_RISK_RATIO = 1.8
HIGH_ERROR_RATE = 0.01


class CloudWatchAnalysis(BaseModel):
    """Summarized production health analysis from CloudWatch metrics."""

    model_config = ConfigDict(frozen=True)

    function_name: str
    window: str
    total_invocations: int
    observed_p50_ms: float | None = None
    observed_p95_ms: float | None = None
    observed_p99_ms: float | None = None
    average_duration_ms: float | None = None
    maximum_duration_ms: float | None = None
    errors: int = 0
    throttles: int = 0
    error_rate: float = Field(ge=0)
    throttle_rate: float = Field(ge=0)
    concurrency_peak: float | None = None
    slo_passed: bool | None = None
    over_provision_signal: bool = False
    risk_signals: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    cost_estimate: CostEstimate
    cold_start_analysis: ColdStartAnalysis | None = None
    provisioned_concurrency_recommendation: ProvisionedConcurrencyRecommendation | None = None


def analyze_cloudwatch_metrics(
    *,
    metrics: LambdaCloudWatchMetrics,
    current_config: LambdaConfig,
    target_p95_ms: float,
    monthly_requests: int,
    window_label: str,
    cold_start_analysis: ColdStartAnalysis | None = None,
) -> CloudWatchAnalysis:
    """Convert CloudWatch metric series into SLO health and recommendation signals."""
    total_invocations = round(_series_sum(metrics.series.get("invocations")))
    errors = round(_series_sum(metrics.series.get("errors")))
    throttles = round(_series_sum(metrics.series.get("throttles")))
    observed_p50_ms = _latest_value(metrics.series.get("duration_p50"))
    observed_p95_ms = _latest_value(metrics.series.get("duration_p95"))
    observed_p99_ms = _latest_value(metrics.series.get("duration_p99"))
    average_duration_ms = _series_average(metrics.series.get("duration_average"))
    maximum_duration_ms = _latest_value(metrics.series.get("duration_maximum"))
    concurrency_peak = _series_max(metrics.series.get("concurrent_executions"))
    error_rate = errors / total_invocations if total_invocations else 0.0
    throttle_rate = throttles / total_invocations if total_invocations else 0.0
    risk_signals = _risk_signals(
        observed_p95_ms=observed_p95_ms,
        observed_p99_ms=observed_p99_ms,
        target_p95_ms=target_p95_ms,
        errors=errors,
        throttles=throttles,
        error_rate=error_rate,
    )
    warnings = _warnings(metrics, observed_p95_ms=observed_p95_ms, observed_p99_ms=observed_p99_ms)
    slo_passed = observed_p95_ms <= target_p95_ms if observed_p95_ms is not None else None
    over_provision_signal = (
        observed_p95_ms is not None
        and observed_p95_ms < target_p95_ms * FAR_BELOW_SLO_RATIO
        and error_rate < HIGH_ERROR_RATE
        and throttles == 0
    )
    recommendations = _recommendations(
        slo_passed=slo_passed,
        over_provision_signal=over_provision_signal,
        risk_signals=risk_signals,
        cold_start_analysis=cold_start_analysis,
    )
    if cold_start_analysis is not None:
        warnings.extend(cold_start_analysis.warnings)

    cost_requests = monthly_requests if monthly_requests > 0 else total_invocations
    cost_estimate = estimate_lambda_cost(
        memory_mb=current_config.memory_mb,
        avg_duration_ms=average_duration_ms or observed_p95_ms or 0,
        monthly_requests=cost_requests,
        architecture=current_config.architecture,
        provisioned_concurrency=current_config.provisioned_concurrency,
    )
    pc_recommendation = (
        recommend_provisioned_concurrency(
            cold_start_rate=cold_start_analysis.cold_start_rate,
            p95_ms=observed_p95_ms,
            p99_ms=observed_p99_ms,
            target_p95_ms=target_p95_ms,
            current_memory_mb=current_config.memory_mb,
            monthly_requests=cost_requests,
            peak_hours_per_month=_observed_hours(metrics),
            architecture=current_config.architecture,
            avg_duration_ms=average_duration_ms,
        )
        if cold_start_analysis is not None
        else None
    )

    return CloudWatchAnalysis(
        function_name=metrics.function_name,
        window=window_label,
        total_invocations=total_invocations,
        observed_p50_ms=observed_p50_ms,
        observed_p95_ms=observed_p95_ms,
        observed_p99_ms=observed_p99_ms,
        average_duration_ms=average_duration_ms,
        maximum_duration_ms=maximum_duration_ms,
        errors=errors,
        throttles=throttles,
        error_rate=error_rate,
        throttle_rate=throttle_rate,
        concurrency_peak=concurrency_peak,
        slo_passed=slo_passed,
        over_provision_signal=over_provision_signal,
        risk_signals=risk_signals,
        recommendations=recommendations,
        warnings=warnings,
        cost_estimate=cost_estimate,
        cold_start_analysis=cold_start_analysis,
        provisioned_concurrency_recommendation=pc_recommendation,
    )


def _risk_signals(
    *,
    observed_p95_ms: float | None,
    observed_p99_ms: float | None,
    target_p95_ms: float,
    errors: int,
    throttles: int,
    error_rate: float,
) -> list[str]:
    signals: list[str] = []
    if observed_p95_ms is not None:
        if observed_p95_ms >= target_p95_ms:
            signals.append("p95 is at or above the SLO target.")
        elif observed_p95_ms >= target_p95_ms * NEAR_SLO_RATIO:
            signals.append("p95 is near the SLO target.")
    if (
        observed_p95_ms
        and observed_p99_ms
        and observed_p99_ms >= observed_p95_ms * P99_TO_P95_RISK_RATIO
    ):
        signals.append("p99 is much higher than p95; investigate cold starts or tail latency.")
    if throttles > 0:
        signals.append("Throttles are present; investigate concurrency limits or traffic spikes.")
    if errors > 0 and error_rate >= HIGH_ERROR_RATE:
        signals.append("Error rate is elevated; investigate function errors.")
    return signals


def _recommendations(
    *,
    slo_passed: bool | None,
    over_provision_signal: bool,
    risk_signals: list[str],
    cold_start_analysis: ColdStartAnalysis | None,
) -> list[str]:
    if (
        cold_start_analysis is not None
        and cold_start_analysis.cold_start_contribution_signal == "likely_cold_start_driven"
    ):
        return [
            "Consider provisioned concurrency if p99 risk appears cold-start-driven.",
            "Run benchmark before changing configuration.",
        ]

    if risk_signals:
        recommendations = ["Run benchmark before changing configuration."]
        if any("Throttles" in signal for signal in risk_signals):
            recommendations.append("Investigate throttles and concurrency settings.")
        if any("Error rate" in signal for signal in risk_signals):
            recommendations.append("Investigate Lambda errors before optimizing cost.")
        if any("p99 is much higher" in signal for signal in risk_signals):
            recommendations.append("Investigate cold starts with logs and CloudWatch metrics.")
        return recommendations

    if over_provision_signal:
        return ["Possible over-provisioning: run benchmark to look for cheaper safe configs."]
    if slo_passed is True:
        return [
            "No immediate change recommended; continue monitoring and benchmark before changes."
        ]
    if slo_passed is None:
        return ["Run benchmark; CloudWatch p95 percentile data was unavailable."]
    return ["Run benchmark; observed p95 appears to violate the SLO."]


def _warnings(
    metrics: LambdaCloudWatchMetrics,
    *,
    observed_p95_ms: float | None,
    observed_p99_ms: float | None,
) -> list[str]:
    warnings: list[str] = []
    if observed_p95_ms is None:
        warnings.append("CloudWatch p95 Duration data was unavailable; SLO status is uncertain.")
    if observed_p99_ms is None:
        warnings.append("CloudWatch p99 Duration data was unavailable; tail risk may be hidden.")
    for metric_id in ("errors", "throttles", "concurrent_executions"):
        if metric_id not in metrics.series or not metrics.series[metric_id].points:
            warnings.append(f"CloudWatch metric '{metric_id}' was unavailable or empty.")
    return warnings


def _series_sum(series: MetricSeries | None) -> float:
    if series is None:
        return 0.0
    return sum(point.value for point in series.points)


def _series_average(series: MetricSeries | None) -> float | None:
    if series is None or not series.points:
        return None
    return sum(point.value for point in series.points) / len(series.points)


def _series_max(series: MetricSeries | None) -> float | None:
    if series is None or not series.points:
        return None
    return max(point.value for point in series.points)


def _latest_value(series: MetricSeries | None) -> float | None:
    if series is None or not series.points:
        return None
    return series.points[-1].value


def _observed_hours(metrics: LambdaCloudWatchMetrics) -> float:
    invocations = metrics.series.get("invocations")
    point_count = len(invocations.points) if invocations is not None else 0
    return max(1.0, metrics.period_seconds * point_count / 3600)
