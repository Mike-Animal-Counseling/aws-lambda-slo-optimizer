"""Provisioned concurrency recommendation logic."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lambdaopt.analysis.cost_model import estimate_lambda_cost

BenefitCategory = Literal["high", "medium", "low", "unknown"]

DEFAULT_CANDIDATE_PC_VALUES = [0, 1, 2, 5, 10]
HIGH_COLD_START_RATE = 0.05
MEDIUM_COLD_START_RATE = 0.01
P99_TARGET_BUFFER = 1.0
P99_TO_P95_GAP_RATIO = 1.8
LOW_TRAFFIC_MONTHLY_REQUESTS = 100_000
PC_DOMINATES_COST_RATIO = 0.6


class ProvisionedConcurrencyRecommendation(BaseModel):
    """Recommendation for testing provisioned concurrency."""

    model_config = ConfigDict(frozen=True)

    recommended_provisioned_concurrency: int
    expected_benefit: BenefitCategory
    monthly_cost_impact_usd: float = Field(ge=0)
    peak_window_cost_usd: float = Field(ge=0)
    always_on_cost_usd: float = Field(ge=0)
    reasoning: str
    warnings: list[str] = Field(default_factory=list)
    candidate_costs_usd: dict[int, float] = Field(default_factory=dict)


def recommend_provisioned_concurrency(
    *,
    cold_start_rate: float,
    p95_ms: float | None,
    p99_ms: float | None,
    target_p95_ms: float,
    current_memory_mb: int,
    monthly_requests: int,
    peak_hours_per_month: float,
    architecture: Literal["x86_64", "arm64"] = "x86_64",
    avg_duration_ms: float | None = None,
    target_p99_ms: float | None = None,
    candidate_pc_values: list[int] | None = None,
    always_on: bool = False,
) -> ProvisionedConcurrencyRecommendation:
    """Recommend whether to test provisioned concurrency for cold-start risk.

    The default recommendation prefers peak-window provisioned concurrency rather
    than always-on capacity because provisioned concurrency runs continuously
    while enabled and can dominate cost at low traffic.
    """
    candidates = candidate_pc_values or DEFAULT_CANDIDATE_PC_VALUES
    selected_pc = _first_positive_pc(candidates)
    duration_ms = avg_duration_ms or p95_ms or 0
    peak_costs = _estimate_candidate_costs(
        candidate_pc_values=candidates,
        memory_mb=current_memory_mb,
        architecture=architecture,
        avg_duration_ms=duration_ms,
        monthly_requests=monthly_requests,
        provisioned_concurrency_hours=peak_hours_per_month,
    )
    always_on_costs = _estimate_candidate_costs(
        candidate_pc_values=candidates,
        memory_mb=current_memory_mb,
        architecture=architecture,
        avg_duration_ms=duration_ms,
        monthly_requests=monthly_requests,
        provisioned_concurrency_hours=730,
    )
    baseline_cost = peak_costs.get(0, 0.0)
    selected_peak_cost = peak_costs.get(selected_pc, baseline_cost)
    selected_always_on_cost = always_on_costs.get(selected_pc, baseline_cost)
    warnings = _cost_warnings(
        monthly_requests=monthly_requests,
        baseline_cost=baseline_cost,
        selected_peak_cost=selected_peak_cost,
        selected_always_on_cost=selected_always_on_cost,
    )

    benefit = _expected_benefit(
        cold_start_rate=cold_start_rate,
        p95_ms=p95_ms,
        p99_ms=p99_ms,
        target_p95_ms=target_p95_ms,
        target_p99_ms=target_p99_ms,
    )
    if benefit in {"low", "unknown"}:
        return ProvisionedConcurrencyRecommendation(
            recommended_provisioned_concurrency=0,
            expected_benefit=benefit,
            monthly_cost_impact_usd=0.0,
            peak_window_cost_usd=baseline_cost,
            always_on_cost_usd=baseline_cost,
            reasoning=_no_pc_reasoning(benefit=benefit, cold_start_rate=cold_start_rate),
            warnings=warnings,
            candidate_costs_usd=peak_costs,
        )

    cost_basis = selected_always_on_cost if always_on else selected_peak_cost
    return ProvisionedConcurrencyRecommendation(
        recommended_provisioned_concurrency=selected_pc,
        expected_benefit=benefit,
        monthly_cost_impact_usd=max(0.0, cost_basis - baseline_cost),
        peak_window_cost_usd=selected_peak_cost,
        always_on_cost_usd=selected_always_on_cost,
        reasoning=(
            f"p95 is within target while p99/cold-start risk suggests testing PC={selected_pc} "
            "during peak windows before considering always-on provisioned concurrency."
        ),
        warnings=warnings,
        candidate_costs_usd=peak_costs,
    )


def _expected_benefit(
    *,
    cold_start_rate: float,
    p95_ms: float | None,
    p99_ms: float | None,
    target_p95_ms: float,
    target_p99_ms: float | None,
) -> BenefitCategory:
    if p95_ms is None or p99_ms is None:
        return "unknown"
    p95_passes = p95_ms <= target_p95_ms
    p99_fails = p99_ms > (target_p99_ms or target_p95_ms * P99_TARGET_BUFFER)
    high_tail_gap = p95_ms > 0 and p99_ms >= p95_ms * P99_TO_P95_GAP_RATIO
    if p95_passes and p99_fails and cold_start_rate >= HIGH_COLD_START_RATE and high_tail_gap:
        return "high"
    if cold_start_rate >= MEDIUM_COLD_START_RATE and (p99_fails or high_tail_gap):
        return "medium"
    return "low"


def _estimate_candidate_costs(
    *,
    candidate_pc_values: list[int],
    memory_mb: int,
    architecture: Literal["x86_64", "arm64"],
    avg_duration_ms: float,
    monthly_requests: int,
    provisioned_concurrency_hours: float,
) -> dict[int, float]:
    return {
        pc: estimate_lambda_cost(
            memory_mb=memory_mb,
            architecture=architecture,
            avg_duration_ms=avg_duration_ms,
            monthly_requests=monthly_requests,
            provisioned_concurrency=pc,
            provisioned_concurrency_hours=provisioned_concurrency_hours if pc > 0 else 0,
        ).total_cost_usd
        for pc in candidate_pc_values
    }


def _first_positive_pc(candidate_pc_values: list[int]) -> int:
    return next((pc for pc in candidate_pc_values if pc > 0), 1)


def _cost_warnings(
    *,
    monthly_requests: int,
    baseline_cost: float,
    selected_peak_cost: float,
    selected_always_on_cost: float,
) -> list[str]:
    warnings: list[str] = []
    if monthly_requests < LOW_TRAFFIC_MONTHLY_REQUESTS:
        warnings.append("Traffic is low; provisioned concurrency capacity cost may dominate.")
    if selected_always_on_cost > 0:
        capacity_delta = max(0.0, selected_always_on_cost - baseline_cost)
        capacity_cost_ratio = capacity_delta / selected_always_on_cost
        if capacity_cost_ratio >= PC_DOMINATES_COST_RATIO:
            warnings.append("Always-on provisioned concurrency cost dominates the estimate.")
    if selected_peak_cost < selected_always_on_cost:
        warnings.append("Prefer peak-window PC over always-on PC unless explicitly required.")
    return warnings


def _no_pc_reasoning(*, benefit: BenefitCategory, cold_start_rate: float) -> str:
    if benefit == "unknown":
        return "Provisioned concurrency benefit is unknown because p95/p99 data is unavailable."
    return (
        f"Cold-start rate is {cold_start_rate:.2%}; provisioned concurrency is not recommended "
        "until cold starts are shown to drive tail latency."
    )
