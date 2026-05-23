"""Markdown report rendering for CloudWatch production analysis."""

from pathlib import Path

from lambdaopt.analysis.cloudwatch_analysis import CloudWatchAnalysis
from lambdaopt.models import LambdaConfig

CLOUDWATCH_REPORT_FILENAME = "optimization_report.md"


def write_cloudwatch_analysis_report(
    *,
    analysis: CloudWatchAnalysis,
    current_config: LambdaConfig,
    target_p95_ms: float,
    monthly_requests: int,
    output_dir: Path,
) -> Path:
    """Write a CloudWatch analysis report to the output directory."""
    path = output_dir / CLOUDWATCH_REPORT_FILENAME
    path.write_text(
        render_cloudwatch_analysis_report(
            analysis=analysis,
            current_config=current_config,
            target_p95_ms=target_p95_ms,
            monthly_requests=monthly_requests,
        ),
        encoding="utf-8",
    )
    return path


def render_cloudwatch_analysis_report(
    *,
    analysis: CloudWatchAnalysis,
    current_config: LambdaConfig,
    target_p95_ms: float,
    monthly_requests: int,
) -> str:
    """Render the CloudWatch production analysis report as Markdown."""
    lines = [
        "# LambdaOpt CloudWatch Analysis Report",
        "",
        "## Current Config",
        "",
        f"- Function: {analysis.function_name}",
        f"- Memory: {current_config.memory_mb} MB",
        f"- Architecture: {current_config.architecture}",
        f"- Timeout: {current_config.timeout_seconds}s",
        f"- Provisioned concurrency: {current_config.provisioned_concurrency}",
        "",
        "## Observation Window",
        "",
        f"- Window: {analysis.window}",
        f"- Target p95 latency: {target_p95_ms:g} ms",
        f"- Monthly request assumption: {monthly_requests:,}",
        "",
        "## Metrics Summary",
        "",
        f"- Total invocations: {analysis.total_invocations:,}",
        f"- Observed p50: {_format_ms(analysis.observed_p50_ms)}",
        f"- Observed p95: {_format_ms(analysis.observed_p95_ms)}",
        f"- Observed p99: {_format_ms(analysis.observed_p99_ms)}",
        f"- Average duration: {_format_ms(analysis.average_duration_ms)}",
        f"- Maximum duration: {_format_ms(analysis.maximum_duration_ms)}",
        f"- Errors: {analysis.errors:,} ({analysis.error_rate:.2%})",
        f"- Throttles: {analysis.throttles:,} ({analysis.throttle_rate:.2%})",
        f"- Peak concurrency: {_format_number(analysis.concurrency_peak)}",
        "",
        "## SLO Health",
        "",
        f"- Status: {_slo_status(analysis.slo_passed)}",
        f"- Possible over-provisioning: {'Yes' if analysis.over_provision_signal else 'No'}",
        "",
        "## Cost Estimate",
        "",
        f"- Estimated monthly requests: {analysis.cost_estimate.monthly_requests:,}",
        f"- Estimated monthly cost: ${analysis.cost_estimate.total_cost_usd:.2f}",
        f"- Cost per million requests: ${analysis.cost_estimate.cost_per_million_requests_usd:.2f}",
        "",
        "## Recommendations",
        "",
        _items_or_none(analysis.recommendations),
        "",
        "## Cold Start Analysis",
        "",
        _cold_start_section(analysis),
        "",
        "## Provisioned Concurrency",
        "",
        _provisioned_concurrency_section(analysis),
        "",
        "## Risk Signals",
        "",
        _items_or_none(analysis.risk_signals),
        "",
        "## Warnings And Limitations",
        "",
        _items_or_none(
            [
                "This report is read-only and does not mutate Lambda configuration.",
                "Lambda automatically sends function metrics to CloudWatch.",
                "Duration percentiles may be unavailable depending on CloudWatch data.",
                *analysis.warnings,
            ]
        ),
        "",
    ]
    return "\n".join(lines)


def _format_ms(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f} ms"


def _format_number(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:g}"


def _slo_status(slo_passed: bool | None) -> str:
    if slo_passed is True:
        return "Healthy"
    if slo_passed is False:
        return "Risky"
    return "Unknown"


def _items_or_none(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def _cold_start_section(analysis: CloudWatchAnalysis) -> str:
    cold = analysis.cold_start_analysis
    if cold is None:
        return "- Not requested. Re-run with `--include-logs` to inspect REPORT Init Duration."

    return "\n".join(
        [
            f"- Total REPORT logs parsed: {cold.total_reports:,}",
            f"- Cold starts: {cold.cold_start_count:,} ({cold.cold_start_rate:.2%})",
            f"- Average Init Duration: {_format_ms(cold.avg_init_duration_ms)}",
            f"- p95 Init Duration: {_format_ms(cold.p95_init_duration_ms)}",
            f"- p99 Init Duration: {_format_ms(cold.p99_init_duration_ms)}",
            f"- Signal: {cold.cold_start_contribution_signal}",
            f"- Diagnosis: {cold.diagnosis}",
            "- Cold-start recommendations:",
            _items_or_none(cold.recommendations),
        ]
    )


def _provisioned_concurrency_section(analysis: CloudWatchAnalysis) -> str:
    recommendation = analysis.provisioned_concurrency_recommendation
    if recommendation is None:
        return "- Not evaluated. Re-run with `--include-logs` to evaluate cold-start-driven PC."

    return "\n".join(
        [
            f"- Recommended PC: {recommendation.recommended_provisioned_concurrency}",
            f"- Expected benefit: {recommendation.expected_benefit}",
            f"- Peak-window monthly cost impact: ${recommendation.monthly_cost_impact_usd:.2f}",
            f"- Peak-window total estimate: ${recommendation.peak_window_cost_usd:.2f}",
            f"- Always-on total estimate: ${recommendation.always_on_cost_usd:.2f}",
            f"- Reasoning: {recommendation.reasoning}",
            "- PC warnings:",
            _items_or_none(recommendation.warnings),
        ]
    )
