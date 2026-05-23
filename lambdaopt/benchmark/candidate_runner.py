"""Benchmark separate candidate Lambda test functions without mutating production."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lambdaopt.benchmark.invoker import (
    DEFAULT_MAX_ATTEMPTS,
    InvocationSample,
    LambdaInvokeClient,
    invoke_lambda_safely,
    load_json_payload,
)
from lambdaopt.benchmark.result_collector import collect_benchmark_result
from lambdaopt.benchmark.runner import _delay_between_invocations, _validate_runner_inputs
from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import BenchmarkResult, LambdaConfig

SEPARATE_TEST_FUNCTIONS_SAFETY_NOTE = (
    "LambdaOpt is benchmarking separate candidate test functions from the mapping file; "
    "it will not mutate memory or architecture on production functions."
)


class CandidateFunctionMapping(BaseModel):
    """Mapping entry from a candidate config to a separate test Lambda function."""

    model_config = ConfigDict(frozen=True)

    function_name: str = Field(min_length=1)
    memory_mb: int = Field(ge=128, le=10240)
    architecture: Literal["x86_64", "arm64"]
    timeout_seconds: int | None = Field(default=None, gt=0)
    provisioned_concurrency: int = Field(default=0, ge=0)
    runtime: str | None = None

    @property
    def config(self) -> LambdaConfig:
        """Return the LambdaConfig represented by this mapping entry."""
        return LambdaConfig(
            memory_mb=self.memory_mb,
            architecture=self.architecture,
            timeout_seconds=self.timeout_seconds,
            provisioned_concurrency=self.provisioned_concurrency,
        )


class CandidateFunctionMappings(BaseModel):
    """Top-level candidate function mapping file schema."""

    model_config = ConfigDict(frozen=True)

    candidates: list[CandidateFunctionMapping] = Field(min_length=1)


def load_candidate_function_mappings(path: Path) -> CandidateFunctionMappings:
    """Load and validate a candidate function mapping file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LambdaOptValidationError(f"Candidate mapping file does not exist: {path}") from exc
    except OSError as exc:
        raise LambdaOptValidationError(f"Could not read candidate mapping file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LambdaOptValidationError(f"Candidate mapping file is not valid JSON: {path}") from exc

    try:
        return CandidateFunctionMappings.model_validate(payload)
    except ValidationError as exc:
        raise LambdaOptValidationError(f"Candidate mapping file has invalid data: {path}") from exc


def run_candidate_function_benchmarks(
    *,
    client: LambdaInvokeClient,
    mappings: CandidateFunctionMappings,
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

    results: list[BenchmarkResult] = []
    for candidate in mappings.candidates:
        samples = _run_candidate_samples(
            client=client,
            function_name=candidate.function_name,
            payload=payload,
            trials=trials,
            warmup=warmup,
            delay_ms=delay_ms,
            max_attempts=max_attempts,
        )
        result = collect_benchmark_result(
            function_name=candidate.function_name,
            config=candidate.config,
            samples=samples,
            runtime=candidate.runtime,
            region=region,
        )
        result.metadata["candidate_function_name"] = candidate.function_name
        result.metadata["safety_note"] = SEPARATE_TEST_FUNCTIONS_SAFETY_NOTE
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
