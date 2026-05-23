"""Adaptive dry-run controller for LambdaOpt watch evaluations."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lambdaopt.models import CostEstimate, LambdaConfig

HIGH_ERROR_RATE = 0.02
THROTTLE_PRESENT_RATE = 0.0
FAR_BELOW_SLO_RATIO = 0.6
NEAR_SLO_RATIO = 0.9
HIGH_COLD_START_RATE = 0.05
P99_TAIL_RISK_RATIO = 1.8
DEFAULT_COOLDOWN_WINDOWS = 2


class ControllerAction(StrEnum):
    """Dry-run controller action names."""

    NO_CHANGE = "NO_CHANGE"
    RUN_BENCHMARK = "RUN_BENCHMARK"
    DOWNSCALE_MEMORY_TEST = "DOWNSCALE_MEMORY_TEST"
    UPSCALE_MEMORY_TEST = "UPSCALE_MEMORY_TEST"
    SWITCH_TO_ARM64_TEST = "SWITCH_TO_ARM64_TEST"
    ENABLE_PROVISIONED_CONCURRENCY_TEST = "ENABLE_PROVISIONED_CONCURRENCY_TEST"
    INVESTIGATE_ERRORS = "INVESTIGATE_ERRORS"
    INVESTIGATE_THROTTLES = "INVESTIGATE_THROTTLES"
    FREEZE_OPTIMIZATION = "FREEZE_OPTIMIZATION"


class CooldownState(BaseModel):
    """Controller cooldown state carried between watch evaluations."""

    model_config = ConfigDict(frozen=True)

    active_action: ControllerAction | None = None
    remaining_windows: int = Field(default=0, ge=0)


class ControllerInput(BaseModel):
    """Inputs for one dry-run adaptive controller evaluation."""

    model_config = ConfigDict(frozen=True)

    current_config: LambdaConfig
    observed_p95_ms: float | None
    observed_p99_ms: float | None
    target_p95_ms: float
    target_p99_ms: float | None = None
    cold_start_rate: float = Field(ge=0)
    error_rate: float = Field(ge=0)
    throttle_rate: float = Field(ge=0)
    current_estimated_cost: CostEstimate
    previous_recommendations: list[ControllerAction] = Field(default_factory=list)
    cooldown_state: CooldownState | None = None


class ControllerDecision(BaseModel):
    """Dry-run controller decision for one watch evaluation."""

    model_config = ConfigDict(frozen=True)

    action: ControllerAction
    reasoning: str
    warnings: list[str] = Field(default_factory=list)
    cooldown_state: CooldownState
    dry_run: bool = True


def evaluate_controller(input_data: ControllerInput) -> ControllerDecision:
    """Evaluate one dry-run watch window and recommend a safe next action."""
    cooldown_decision = _decision_from_cooldown(input_data)
    if cooldown_decision is not None:
        return cooldown_decision

    action, reasoning = _select_action(input_data)
    warnings = [
        "Dry run only: LambdaOpt will not mutate production infrastructure.",
        "Controller actions are recommendations for tests or investigations, not direct changes.",
    ]
    return ControllerDecision(
        action=action,
        reasoning=reasoning,
        warnings=warnings,
        cooldown_state=_next_cooldown_state(action),
    )


def _decision_from_cooldown(input_data: ControllerInput) -> ControllerDecision | None:
    cooldown = input_data.cooldown_state
    if cooldown is None or cooldown.remaining_windows == 0 or cooldown.active_action is None:
        return None
    next_cooldown = CooldownState(
        active_action=cooldown.active_action,
        remaining_windows=max(0, cooldown.remaining_windows - 1),
    )
    return ControllerDecision(
        action=ControllerAction.NO_CHANGE,
        reasoning=(
            f"Cooldown active after {cooldown.active_action}; holding recommendation to "
            "avoid oscillation."
        ),
        warnings=["Dry run only: cooldown prevented repeated optimization actions."],
        cooldown_state=next_cooldown,
    )


def _select_action(input_data: ControllerInput) -> tuple[ControllerAction, str]:
    if input_data.error_rate >= HIGH_ERROR_RATE:
        return (
            ControllerAction.FREEZE_OPTIMIZATION,
            "High error rate detected; freeze optimization before performance or cost changes.",
        )
    if input_data.throttle_rate > THROTTLE_PRESENT_RATE:
        return (
            ControllerAction.INVESTIGATE_THROTTLES,
            "Throttles are present; investigate concurrency and traffic before "
            "memory optimization.",
        )
    if input_data.observed_p95_ms is None:
        return (
            ControllerAction.RUN_BENCHMARK,
            "p95 is unavailable; run benchmark or improve metrics before changing configuration.",
        )

    if (
        input_data.observed_p95_ms < input_data.target_p95_ms * FAR_BELOW_SLO_RATIO
        and input_data.cold_start_rate < HIGH_COLD_START_RATE
        and input_data.error_rate < HIGH_ERROR_RATE
    ):
        return (
            ControllerAction.DOWNSCALE_MEMORY_TEST,
            "p95 is far below SLO with low cold starts and errors; test a cheaper memory config.",
        )

    if input_data.observed_p95_ms > input_data.target_p95_ms:
        if input_data.cold_start_rate >= HIGH_COLD_START_RATE:
            return (
                ControllerAction.ENABLE_PROVISIONED_CONCURRENCY_TEST,
                "p95 violates SLO and cold-start rate is high; test provisioned concurrency.",
            )
        return (
            ControllerAction.UPSCALE_MEMORY_TEST,
            "p95 violates SLO with low cold-start rate; test higher memory or run benchmark.",
        )

    if input_data.observed_p95_ms >= input_data.target_p95_ms * NEAR_SLO_RATIO:
        if _has_tail_risk(input_data):
            return (
                ControllerAction.RUN_BENCHMARK,
                "p95 is near SLO and p99 tail risk is present; benchmark before changes.",
            )
        return (
            ControllerAction.NO_CHANGE,
            "p95 is near SLO but no strong risk signal requires action.",
        )

    return ControllerAction.NO_CHANGE, "SLO appears healthy; no action recommended."


def _has_tail_risk(input_data: ControllerInput) -> bool:
    if input_data.observed_p95_ms is None or input_data.observed_p99_ms is None:
        return False
    target_p99 = input_data.target_p99_ms
    if target_p99 is not None and input_data.observed_p99_ms > target_p99:
        return True
    return input_data.observed_p99_ms >= input_data.observed_p95_ms * P99_TAIL_RISK_RATIO


def _next_cooldown_state(action: ControllerAction) -> CooldownState:
    if action in {
        ControllerAction.DOWNSCALE_MEMORY_TEST,
        ControllerAction.UPSCALE_MEMORY_TEST,
        ControllerAction.SWITCH_TO_ARM64_TEST,
        ControllerAction.ENABLE_PROVISIONED_CONCURRENCY_TEST,
    }:
        return CooldownState(active_action=action, remaining_windows=DEFAULT_COOLDOWN_WINDOWS)
    return CooldownState()
