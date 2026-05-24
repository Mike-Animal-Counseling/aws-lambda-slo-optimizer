"""Markdown optimization report rendering."""

from pathlib import Path

from lambdaopt.models import AnalyzedConfig, Recommendation
from lambdaopt.security import redact_text

MARKDOWN_REPORT_FILENAME = "optimization_report.md"


def write_markdown_report(
    *,
    analyzed_configs: list[AnalyzedConfig],
    recommendation: Recommendation,
    target_p95_ms: float,
    monthly_requests: int,
    output_dir: Path,
    warnings: list[str] | None = None,
) -> Path:
    """Write a human-readable optimization report."""
    path = output_dir / MARKDOWN_REPORT_FILENAME
    rendered = render_markdown_report(
        analyzed_configs=analyzed_configs,
        recommendation=recommendation,
        target_p95_ms=target_p95_ms,
        monthly_requests=monthly_requests,
        warnings=warnings or [],
    )
    path.write_text(redact_text(rendered), encoding="utf-8")
    return path


def render_markdown_report(
    *,
    analyzed_configs: list[AnalyzedConfig],
    recommendation: Recommendation,
    target_p95_ms: float,
    monthly_requests: int,
    warnings: list[str],
) -> str:
    """Render the optimization report as Markdown."""
    recommended = recommendation.recommended_config
    all_warnings = [*recommendation.warnings, *warnings]

    lines = [
        "# LambdaOpt Optimization Report",
        "",
        "## Target SLO",
        "",
        f"- p95 latency target: {target_p95_ms:g} ms",
        f"- Monthly request assumption: {monthly_requests:,}",
        "",
        "## Recommendation",
        "",
        f"- Memory: {recommended.memory_mb} MB",
        f"- Architecture: {recommended.architecture}",
        f"- Provisioned concurrency: {recommended.provisioned_concurrency}",
        f"- Confidence: {recommendation.confidence:.0%}",
        "",
        "## Why This Config Was Selected",
        "",
        recommendation.reason_summary,
        "",
        "## Benchmark Results",
        "",
        _benchmark_table(analyzed_configs),
        "",
        "## Rejected Configs",
        "",
        _rejected_reasons(recommendation),
        "",
        "## Warnings And Limitations",
        "",
        _warnings(all_warnings),
        "",
        "## Next Steps",
        "",
        "- Run a larger benchmark sample before production rollout.",
        "- Compare results against CloudWatch metrics once AWS integrations are enabled.",
        "- Re-run tuning after meaningful traffic, code, dependency, or runtime changes.",
        "",
    ]
    return "\n".join(lines)


def _benchmark_table(analyzed_configs: list[AnalyzedConfig]) -> str:
    header = (
        "| Candidate | Function ref | Source | Memory | Arch | p50 | p95 | p99 | "
        "Cold start rate | Monthly cost | SLO | Pareto |\n"
        "|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---|"
    )
    rows = [
        (
            f"| {_candidate_name(config)} "
            f"| {_candidate_function_ref(config)} "
            f"| {_candidate_source(config)} "
            f"| {config.config.memory_mb} MB "
            f"| {config.config.architecture} "
            f"| {config.latency.p50_ms:.1f} ms "
            f"| {config.latency.p95_ms:.1f} ms "
            f"| {config.latency.p99_ms:.1f} ms "
            f"| {config.cold_start_rate:.1%} "
            f"| ${config.cost.total_cost_usd:.2f} "
            f"| {'Pass' if config.slo_passed and config.errors == 0 else 'Fail'} "
            f"| {'Dominated' if config.dominated else 'Frontier'} |"
        )
        for config in sorted(
            analyzed_configs,
            key=lambda item: (item.cost.total_cost_usd, item.latency.p95_ms),
        )
    ]
    return "\n".join([header, *rows])


def _candidate_name(config: AnalyzedConfig) -> str:
    return str(config.metadata.get("candidate_name", "-"))


def _candidate_function_ref(config: AnalyzedConfig) -> str:
    return str(
        config.metadata.get(
            "candidate_function_ref",
            config.metadata.get("candidate_function_name", "-"),
        )
    )


def _candidate_source(config: AnalyzedConfig) -> str:
    return str(config.metadata.get("candidate_source", "-"))


def _rejected_reasons(recommendation: Recommendation) -> str:
    if not recommendation.rejected_reasons:
        return "- No rejected configurations."

    return "\n".join(
        f"- `{config_key}`: {reason}"
        for config_key, reason in sorted(recommendation.rejected_reasons.items())
    )


def _warnings(warnings: list[str]) -> str:
    base_warnings = [
        "Cost estimates are local approximations and exclude account-specific discounts.",
        "No AWS APIs were called; results depend entirely on the input benchmark file.",
    ]
    return "\n".join(f"- {warning}" for warning in [*base_warnings, *warnings])
