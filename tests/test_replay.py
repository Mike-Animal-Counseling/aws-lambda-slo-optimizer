from lambdaopt.models import CostEstimate, LambdaConfig
from lambdaopt.recommend.controller import ControllerAction, ControllerInput
from lambdaopt.simulator.replay import MetricWindow, replay_controller_windows


def test_replay_controller_windows_uses_cooldown_to_prevent_oscillation() -> None:
    base_input = ControllerInput(
        current_config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        observed_p95_ms=None,
        observed_p99_ms=None,
        target_p95_ms=500,
        cold_start_rate=0,
        error_rate=0,
        throttle_rate=0,
        current_estimated_cost=CostEstimate(
            monthly_requests=1_000_000,
            request_cost_usd=0.2,
            compute_cost_usd=1.0,
            provisioned_concurrency_cost_usd=0,
            total_cost_usd=1.2,
            cost_per_million_requests_usd=1.2,
        ),
    )
    windows = [
        MetricWindow(observed_p95_ms=200, observed_p99_ms=260, cold_start_rate=0),
        MetricWindow(observed_p95_ms=210, observed_p99_ms=270, cold_start_rate=0),
        MetricWindow(observed_p95_ms=220, observed_p99_ms=280, cold_start_rate=0),
    ]

    decisions = replay_controller_windows(base_input=base_input, windows=windows)

    assert decisions[0].action == ControllerAction.DOWNSCALE_MEMORY_TEST
    assert decisions[1].action == ControllerAction.NO_CHANGE
    assert decisions[2].action == ControllerAction.NO_CHANGE
    assert "Cooldown active" in decisions[1].reasoning
