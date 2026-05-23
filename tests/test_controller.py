from lambdaopt.models import CostEstimate, LambdaConfig
from lambdaopt.recommend.controller import (
    ControllerAction,
    ControllerInput,
    CooldownState,
    evaluate_controller,
)


def test_over_provision_case_recommends_downscale_memory_test() -> None:
    decision = evaluate_controller(
        _controller_input(observed_p95_ms=200, observed_p99_ms=260, target_p95_ms=500)
    )

    assert decision.action == ControllerAction.DOWNSCALE_MEMORY_TEST
    assert decision.dry_run is True


def test_slo_violation_due_to_cold_starts_recommends_pc_test() -> None:
    decision = evaluate_controller(
        _controller_input(
            observed_p95_ms=650,
            observed_p99_ms=1400,
            target_p95_ms=500,
            cold_start_rate=0.12,
        )
    )

    assert decision.action == ControllerAction.ENABLE_PROVISIONED_CONCURRENCY_TEST


def test_slo_violation_due_to_execution_latency_recommends_upscale_test() -> None:
    decision = evaluate_controller(
        _controller_input(
            observed_p95_ms=650,
            observed_p99_ms=720,
            target_p95_ms=500,
            cold_start_rate=0.001,
        )
    )

    assert decision.action == ControllerAction.UPSCALE_MEMORY_TEST


def test_high_error_rate_freezes_optimization() -> None:
    decision = evaluate_controller(
        _controller_input(observed_p95_ms=200, target_p95_ms=500, error_rate=0.05)
    )

    assert decision.action == ControllerAction.FREEZE_OPTIMIZATION


def test_throttles_produce_investigate_action() -> None:
    decision = evaluate_controller(
        _controller_input(observed_p95_ms=200, target_p95_ms=500, throttle_rate=0.01)
    )

    assert decision.action == ControllerAction.INVESTIGATE_THROTTLES


def test_cooldown_prevents_repeated_change_action() -> None:
    decision = evaluate_controller(
        _controller_input(
            observed_p95_ms=650,
            target_p95_ms=500,
            cooldown_state=CooldownState(
                active_action=ControllerAction.UPSCALE_MEMORY_TEST,
                remaining_windows=2,
            ),
        )
    )

    assert decision.action == ControllerAction.NO_CHANGE
    assert decision.cooldown_state.remaining_windows == 1
    assert "Cooldown active" in decision.reasoning


def _controller_input(
    *,
    observed_p95_ms: float | None,
    target_p95_ms: float,
    observed_p99_ms: float | None = None,
    cold_start_rate: float = 0,
    error_rate: float = 0,
    throttle_rate: float = 0,
    cooldown_state: CooldownState | None = None,
) -> ControllerInput:
    return ControllerInput(
        current_config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        observed_p95_ms=observed_p95_ms,
        observed_p99_ms=observed_p99_ms,
        target_p95_ms=target_p95_ms,
        cold_start_rate=cold_start_rate,
        error_rate=error_rate,
        throttle_rate=throttle_rate,
        current_estimated_cost=CostEstimate(
            monthly_requests=1_000_000,
            request_cost_usd=0.2,
            compute_cost_usd=1.0,
            provisioned_concurrency_cost_usd=0,
            total_cost_usd=1.2,
            cost_per_million_requests_usd=1.2,
        ),
        cooldown_state=cooldown_state,
    )
