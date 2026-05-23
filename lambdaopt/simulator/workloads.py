"""Synthetic workload definitions for local LambdaOpt simulations."""

from dataclasses import dataclass
from typing import Literal

WorkloadName = Literal["cpu-bound", "io-bound", "cold-start-heavy"]

MEMORY_CANDIDATES_MB = (512, 1024, 1536, 2048)
ARCHITECTURE_CANDIDATES: tuple[Literal["x86_64", "arm64"], ...] = ("x86_64", "arm64")


@dataclass(frozen=True)
class WorkloadProfile:
    """Parameters that shape synthetic benchmark latency samples."""

    name: WorkloadName
    base_duration_ms: float
    memory_exponent: float
    jitter_ratio: float
    arm64_speedup_ratio: float
    cold_start_rate: float
    cold_start_penalty_ms: float
    io_floor_ms: float = 0.0


CPU_BOUND_PROFILE = WorkloadProfile(
    name="cpu-bound",
    base_duration_ms=640.0,
    memory_exponent=0.9,
    jitter_ratio=0.08,
    arm64_speedup_ratio=0.12,
    cold_start_rate=0.03,
    cold_start_penalty_ms=180.0,
)

IO_BOUND_PROFILE = WorkloadProfile(
    name="io-bound",
    base_duration_ms=130.0,
    memory_exponent=0.12,
    jitter_ratio=0.06,
    arm64_speedup_ratio=0.04,
    cold_start_rate=0.02,
    cold_start_penalty_ms=140.0,
    io_floor_ms=260.0,
)

COLD_START_HEAVY_PROFILE = WorkloadProfile(
    name="cold-start-heavy",
    base_duration_ms=260.0,
    memory_exponent=0.45,
    jitter_ratio=0.07,
    arm64_speedup_ratio=0.08,
    cold_start_rate=0.18,
    cold_start_penalty_ms=850.0,
)

WORKLOAD_PROFILES: dict[WorkloadName, WorkloadProfile] = {
    "cpu-bound": CPU_BOUND_PROFILE,
    "io-bound": IO_BOUND_PROFILE,
    "cold-start-heavy": COLD_START_HEAVY_PROFILE,
}


def get_workload_profile(workload: WorkloadName) -> WorkloadProfile:
    """Return the simulator profile for a supported workload name."""
    return WORKLOAD_PROFILES[workload]
