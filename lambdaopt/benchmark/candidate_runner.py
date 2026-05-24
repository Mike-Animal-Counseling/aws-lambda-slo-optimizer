"""Benchmark separate candidate Lambda test functions without mutating production."""

from pathlib import Path

from lambdaopt.benchmark.candidate_schema import (
    CandidateMapping,
    CandidateMappings,
    load_candidate_mappings,
)
from lambdaopt.benchmark.invoker import (
    DEFAULT_MAX_ATTEMPTS,
    InvocationSample,
    LambdaInvokeClient,
    invoke_lambda_safely,
    load_json_payload,
)
from lambdaopt.benchmark.result_collector import collect_benchmark_result
from lambdaopt.benchmark.runner import _delay_between_invocations, _validate_runner_inputs
from lambdaopt.models import BenchmarkResult
from lambdaopt.security import payload_metadata

SEPARATE_TEST_FUNCTIONS_SAFETY_NOTE = (
    "LambdaOpt is benchmarking candidate aliases or separate candidate test functions from the "
    "mapping file; it will not mutate Lambda memory, architecture, aliases, or production "
    "configuration."
)

CandidateFunctionMapping = CandidateMapping
CandidateFunctionMappings = CandidateMappings


def load_candidate_function_mappings(
    path: Path,
    *,
    allow_production_candidate: bool = False,
) -> CandidateMappings:
    """Load and validate a candidate function mapping file."""
    return load_candidate_mappings(
        path,
        allow_production_candidate=allow_production_candidate,
    )


def run_candidate_function_benchmarks(
    *,
    client: LambdaInvokeClient,
    mappings: CandidateMappings,
    payload_path: Path,
    trials: int,
    region: str | None = None,
    warmup: int = 0,
    delay_ms: int = 0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> list[BenchmarkResult]:
    """Benchmark each mapped test function and return BenchmarkResult objects."""
    _validate_runner_inputs(trials=trials, warmup=warmup, delay_ms=delay_ms)
    payload = load_json_payload(payload_path)
    safe_payload_metadata = payload_metadata(payload_path)

    results: list[BenchmarkResult] = []
    for candidate in mappings.candidates:
        samples = _run_candidate_samples(
            client=client,
            function_name=candidate.function_ref,
            payload=payload,
            trials=trials,
            warmup=warmup,
            delay_ms=delay_ms,
            max_attempts=max_attempts,
        )
        result = collect_benchmark_result(
            function_name=candidate.function_ref,
            config=candidate.config,
            samples=samples,
            runtime=candidate.runtime,
            region=region,
        )
        result.metadata["candidate_name"] = candidate.name
        result.metadata["candidate_function_ref"] = candidate.function_ref
        result.metadata["candidate_source"] = candidate.source_type
        result.metadata["candidate_function_name"] = candidate.function_ref
        result.metadata["safety_note"] = SEPARATE_TEST_FUNCTIONS_SAFETY_NOTE
        result.metadata["payload"] = safe_payload_metadata
        if candidate.notes:
            result.metadata["candidate_notes"] = candidate.notes
        if candidate.tags:
            result.metadata["candidate_tags"] = candidate.tags
        result.metadata["warmup_invocations"] = warmup
        result.metadata["delay_ms"] = delay_ms
        results.append(result)

    return results


def _run_candidate_samples(
    *,
    client: LambdaInvokeClient,
    function_name: str,
    payload: bytes,
    trials: int,
    warmup: int,
    delay_ms: int,
    max_attempts: int,
) -> list[InvocationSample]:
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

    return samples
