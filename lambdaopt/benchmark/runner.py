"""Benchmark runner for the currently deployed Lambda configuration."""

import time
from pathlib import Path

from lambdaopt.benchmark.invoker import (
    DEFAULT_MAX_ATTEMPTS,
    InvocationSample,
    LambdaInvokeClient,
    invoke_lambda_safely,
    load_json_payload,
)
from lambdaopt.benchmark.result_collector import collect_benchmark_result
from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import BenchmarkResult, LambdaConfig
from lambdaopt.security import payload_metadata

CURRENT_CONFIG_ONLY_WARNING = (
    "This benchmark invokes only the currently deployed Lambda configuration. "
    "It does not compare alternate memory or architecture settings yet."
)


def run_current_config_benchmark(
    *,
    client: LambdaInvokeClient,
    function_name: str,
    config: LambdaConfig,
    payload_path: Path,
    trials: int,
    runtime: str | None = None,
    region: str | None = None,
    warmup: int = 0,
    delay_ms: int = 0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> BenchmarkResult:
    """Invoke the currently deployed function N times and collect latency samples."""
    _validate_runner_inputs(trials=trials, warmup=warmup, delay_ms=delay_ms)
    payload = load_json_payload(payload_path)

    for _ in range(warmup):
        invoke_lambda_safely(
            client=client,
            function_name=function_name,
            payload=payload,
            max_attempts=max_attempts,
        )
        _delay_between_invocations(delay_ms)

    samples: list[InvocationSample] = []
    for _ in range(trials):
        samples.append(
            invoke_lambda_safely(
                client=client,
                function_name=function_name,
                payload=payload,
                max_attempts=max_attempts,
            )
        )
        _delay_between_invocations(delay_ms)

    result = collect_benchmark_result(
        function_name=function_name,
        config=config,
        samples=samples,
        runtime=runtime,
        region=region,
    )
    result.metadata["warning_current_config_only"] = CURRENT_CONFIG_ONLY_WARNING
    result.metadata["payload"] = payload_metadata(payload_path)
    result.metadata["warmup_invocations"] = warmup
    result.metadata["delay_ms"] = delay_ms
    return result


def _validate_runner_inputs(*, trials: int, warmup: int, delay_ms: int) -> None:
    if trials <= 0:
        raise LambdaOptValidationError("trials must be positive.")
    if warmup < 0:
        raise LambdaOptValidationError("warmup must be non-negative.")
    if delay_ms < 0:
        raise LambdaOptValidationError("delay-ms must be non-negative.")


def _delay_between_invocations(delay_ms: int) -> None:
    if delay_ms > 0:
        time.sleep(delay_ms / 1000)
