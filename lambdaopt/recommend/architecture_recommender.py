"""Architecture comparison and recommendation helpers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from lambdaopt.models import AnalyzedConfig

ArchitectureRecommendationStatus = Literal[
    "clearly_better",
    "cheaper_but_slower_within_slo",
    "risky_due_to_slower_latency",
    "unknown_due_to_missing_comparison_data",
]

ARM64_COMPATIBILITY_WARNING = (
    "Native dependencies, compiled packages, layers, and container images must be "
    "compatible with arm64 before switching. Do not automatically switch architectures "
    "without validation."
)


class ArchitectureComparison(BaseModel):
    """Comparison of x86_64 and arm64 at the same Lambda memory size."""

    model_config = ConfigDict(frozen=True)

    memory_mb: int
    status: ArchitectureRecommendationStatus
    latency_difference_ms: float | None
    cost_difference_usd: float | None
    arm64_p95_ms: float | None
    x86_p95_ms: float | None
    arm64_cost_usd: float | None
    x86_cost_usd: float | None
    reasoning: str
    warnings: list[str]


def compare_architectures_by_memory(
    analyzed_configs: list[AnalyzedConfig],
    *,
    target_p95_ms: float,
) -> dict[int, ArchitectureComparison]:
    """Compare x86_64 and arm64 configs grouped by memory size."""
    memory_values = sorted({config.config.memory_mb for config in analyzed_configs})
    return {
        memory_mb: compare_architecture_pair(
            analyzed_configs,
            memory_mb=memory_mb,
            target_p95_ms=target_p95_ms,
        )
        for memory_mb in memory_values
    }


def compare_architecture_pair(
    analyzed_configs: list[AnalyzedConfig],
    *,
    memory_mb: int,
    target_p95_ms: float,
) -> ArchitectureComparison:
    """Compare x86_64 and arm64 for one memory size."""
    x86 = _find_config(analyzed_configs, memory_mb=memory_mb, architecture="x86_64")
    arm64 = _find_config(analyzed_configs, memory_mb=memory_mb, architecture="arm64")
    if x86 is None or arm64 is None:
        return ArchitectureComparison(
            memory_mb=memory_mb,
            status="unknown_due_to_missing_comparison_data",
            latency_difference_ms=None,
            cost_difference_usd=None,
            arm64_p95_ms=arm64.latency.p95_ms if arm64 else None,
            x86_p95_ms=x86.latency.p95_ms if x86 else None,
            arm64_cost_usd=arm64.cost.total_cost_usd if arm64 else None,
            x86_cost_usd=x86.cost.total_cost_usd if x86 else None,
            reasoning="Cannot compare architectures because one side of the pair is missing.",
            warnings=[ARM64_COMPATIBILITY_WARNING],
        )

    latency_difference_ms = arm64.latency.p95_ms - x86.latency.p95_ms
    cost_difference_usd = arm64.cost.total_cost_usd - x86.cost.total_cost_usd
    arm64_cheaper = cost_difference_usd < 0
    arm64_faster_or_equal = latency_difference_ms <= 0
    arm64_passes_slo = arm64.latency.p95_ms <= target_p95_ms and arm64.errors == 0

    if arm64_cheaper and arm64_faster_or_equal and arm64_passes_slo:
        status: ArchitectureRecommendationStatus = "clearly_better"
        reasoning = (
            "arm64 is lower cost, benchmarked latency is at least as good as x86_64, "
            "and it satisfies the SLO."
        )
    elif arm64_cheaper and arm64_passes_slo:
        status = "cheaper_but_slower_within_slo"
        reasoning = (
            "arm64 is lower cost and satisfies the SLO, but benchmarked latency is slower "
            "than x86_64 at the same memory."
        )
    elif arm64_cheaper:
        status = "risky_due_to_slower_latency"
        reasoning = (
            "arm64 is lower cost but benchmarked latency does not safely satisfy the SLO."
        )
    else:
        status = "risky_due_to_slower_latency"
        reasoning = "arm64 is not clearly lower cost for this memory size."

    return ArchitectureComparison(
        memory_mb=memory_mb,
        status=status,
        latency_difference_ms=latency_difference_ms,
        cost_difference_usd=cost_difference_usd,
        arm64_p95_ms=arm64.latency.p95_ms,
        x86_p95_ms=x86.latency.p95_ms,
        arm64_cost_usd=arm64.cost.total_cost_usd,
        x86_cost_usd=x86.cost.total_cost_usd,
        reasoning=reasoning,
        warnings=[ARM64_COMPATIBILITY_WARNING],
    )


def arm64_recommendation_reason(
    analyzed_configs: list[AnalyzedConfig],
    *,
    memory_mb: int,
    target_p95_ms: float,
) -> tuple[str | None, list[str]]:
    """Return arm64-specific reason and warnings for a selected arm64 config."""
    comparison = compare_architecture_pair(
        analyzed_configs,
        memory_mb=memory_mb,
        target_p95_ms=target_p95_ms,
    )
    if comparison.status in {"clearly_better", "cheaper_but_slower_within_slo"}:
        return (
            "Architecture note: arm64 satisfies the SLO, has lower estimated cost, "
            "and benchmarked latency is acceptable; compatibility must be verified.",
            comparison.warnings,
        )
    return None, comparison.warnings


def _find_config(
    analyzed_configs: list[AnalyzedConfig],
    *,
    memory_mb: int,
    architecture: Literal["x86_64", "arm64"],
) -> AnalyzedConfig | None:
    return next(
        (
            config
            for config in analyzed_configs
            if config.config.memory_mb == memory_mb
            and config.config.architecture == architecture
        ),
        None,
    )
