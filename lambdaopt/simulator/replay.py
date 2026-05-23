"""Replay synthetic benchmark results through the local optimizer workflow."""

from pydantic import BaseModel, ConfigDict, Field

from lambdaopt.models import BenchmarkResult
from lambdaopt.recommend.controller import (
    ControllerDecision,
    ControllerInput,
    evaluate_controller,
)
from lambdaopt.simulator.generator import (
    DEFAULT_SAMPLE_COUNT,
    DEFAULT_SEED,
    generate_benchmark_results,
)
from lambdaopt.simulator.workloads import WorkloadName

COLD_START_RISK_WARNING = (
    "Cold-start-heavy simulations include high p99 and cold-start samples; "
    "CloudWatch metrics and cold-start log analysis are recommended before production rollout."
)


def replay_workload(
    *,
    workload: WorkloadName,
    samples: int = DEFAULT_SAMPLE_COUNT,
    seed: int = DEFAULT_SEED,
) -> tuple[list[BenchmarkResult], list[str]]:
    """Generate benchmark results and workflow warnings for a synthetic workload."""
    benchmark_results = generate_benchmark_results(
        workload=workload,
        samples=samples,
        seed=seed,
    )
    warnings = [COLD_START_RISK_WARNING] if workload == "cold-start-heavy" else []
    return benchmark_results, warnings


class MetricWindow(BaseModel):
    """Synthetic metric window for controller replay."""

    model_config = ConfigDict(frozen=True)

    observed_p95_ms: float | None
    observed_p99_ms: float | None = None
    cold_start_rate: float = Field(default=0, ge=0)
    error_rate: float = Field(default=0, ge=0)
    throttle_rate: float = Field(default=0, ge=0)


def replay_controller_windows(
    *,
    base_input: ControllerInput,
    windows: list[MetricWindow],
) -> list[ControllerDecision]:
    """Replay controller decisions over metric windows with cooldown state."""
    decisions: list[ControllerDecision] = []
    cooldown = base_input.cooldown_state
    for window in windows:
        decision = evaluate_controller(
            base_input.model_copy(
                update={
                    "observed_p95_ms": window.observed_p95_ms,
                    "observed_p99_ms": window.observed_p99_ms,
                    "cold_start_rate": window.cold_start_rate,
                    "error_rate": window.error_rate,
                    "throttle_rate": window.throttle_rate,
                    "cooldown_state": cooldown,
                }
            )
        )
        decisions.append(decision)
        cooldown = decision.cooldown_state

    return decisions
