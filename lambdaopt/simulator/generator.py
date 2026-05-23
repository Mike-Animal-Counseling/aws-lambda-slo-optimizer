"""Synthetic benchmark result generation."""

from random import Random
from typing import Literal

from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import BenchmarkResult, LambdaConfig
from lambdaopt.simulator.workloads import (
    ARCHITECTURE_CANDIDATES,
    MEMORY_CANDIDATES_MB,
    WorkloadName,
    WorkloadProfile,
    get_workload_profile,
)

DEFAULT_SAMPLE_COUNT = 100
DEFAULT_SEED = 7
MIN_LATENCY_MS = 1.0
BASELINE_MEMORY_MB = 512


def generate_benchmark_results(
    *,
    workload: WorkloadName,
    samples: int = DEFAULT_SAMPLE_COUNT,
    seed: int = DEFAULT_SEED,
) -> list[BenchmarkResult]:
    """Generate synthetic benchmark results for every candidate configuration."""
    if samples <= 0:
        raise LambdaOptValidationError("samples must be positive.")

    profile = get_workload_profile(workload)
    rng = Random(seed)
    results: list[BenchmarkResult] = []

    for memory_mb in MEMORY_CANDIDATES_MB:
        for architecture in ARCHITECTURE_CANDIDATES:
            latencies, cold_starts = _generate_latency_samples(
                profile=profile,
                memory_mb=memory_mb,
                architecture=architecture,
                samples=samples,
                rng=rng,
            )
            results.append(
                BenchmarkResult(
                    config=LambdaConfig(memory_mb=memory_mb, architecture=architecture),
                    raw_latencies_ms=latencies,
                    cold_starts=cold_starts,
                    errors=0,
                    metadata={
                        "source": "simulator",
                        "workload": workload,
                        "seed": seed,
                        "samples": samples,
                    },
                )
            )

    return results


def _generate_latency_samples(
    *,
    profile: WorkloadProfile,
    memory_mb: int,
    architecture: Literal["x86_64", "arm64"],
    samples: int,
    rng: Random,
) -> tuple[list[float], int]:
    warm_mean_ms = _warm_mean_latency_ms(profile, memory_mb, architecture)
    cold_starts = (
        max(1, round(samples * profile.cold_start_rate))
        if profile.cold_start_rate
        else 0
    )
    cold_indexes = set(rng.sample(range(samples), cold_starts)) if cold_starts else set()

    latencies: list[float] = []
    for index in range(samples):
        latency_ms = rng.gauss(warm_mean_ms, warm_mean_ms * profile.jitter_ratio)
        if index in cold_indexes:
            latency_ms += profile.cold_start_penalty_ms * rng.uniform(0.85, 1.2)
        latencies.append(round(max(MIN_LATENCY_MS, latency_ms), 3))

    return latencies, cold_starts


def _warm_mean_latency_ms(
    profile: WorkloadProfile,
    memory_mb: int,
    architecture: Literal["x86_64", "arm64"],
) -> float:
    memory_ratio = memory_mb / BASELINE_MEMORY_MB
    memory_sensitive_duration = profile.base_duration_ms / (memory_ratio**profile.memory_exponent)
    warm_mean_ms = float(profile.io_floor_ms + memory_sensitive_duration)

    if architecture == "arm64":
        warm_mean_ms *= 1 - profile.arm64_speedup_ratio

    return warm_mean_ms
