"""Typed domain models shared across LambdaOpt modules."""

from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

NonNegativeMilliseconds: TypeAlias = Annotated[float, Field(ge=0)]


class LatencyPercentile(StrEnum):
    """Supported latency percentile targets for SLO checks."""

    P95 = "p95"
    P99 = "p99"


class LatencySLO(BaseModel):
    """A user-defined Lambda latency service-level objective."""

    model_config = ConfigDict(frozen=True)

    percentile: LatencyPercentile
    threshold_ms: float = Field(gt=0, description="Maximum allowed latency in milliseconds.")


class LambdaConfig(BaseModel):
    """AWS Lambda runtime settings for a benchmarked or recommended configuration."""

    model_config = ConfigDict(frozen=True)

    memory_mb: int = Field(ge=128, le=10240)
    architecture: Literal["x86_64", "arm64"]
    timeout_seconds: int | None = Field(default=None, gt=0)
    provisioned_concurrency: int = Field(default=0, ge=0)


class LatencyStats(BaseModel):
    """Aggregated latency statistics for a Lambda configuration."""

    model_config = ConfigDict(frozen=True)

    mean_ms: NonNegativeMilliseconds
    p50_ms: NonNegativeMilliseconds
    p95_ms: NonNegativeMilliseconds
    p99_ms: NonNegativeMilliseconds
    min_ms: NonNegativeMilliseconds
    max_ms: NonNegativeMilliseconds
    stddev_ms: NonNegativeMilliseconds
    sample_count: int = Field(ge=0)
    slo_violation_rate: float = Field(ge=0, le=1)


class BenchmarkResult(BaseModel):
    """Raw local benchmark result for one Lambda configuration candidate."""

    model_config = ConfigDict(frozen=True)

    config: LambdaConfig
    raw_latencies_ms: list[NonNegativeMilliseconds] = Field(min_length=1)
    cold_starts: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostEstimate(BaseModel):
    """Estimated Lambda cost for a configuration over a monthly traffic volume."""

    model_config = ConfigDict(frozen=True)

    monthly_requests: int = Field(ge=0)
    request_cost_usd: float = Field(ge=0)
    compute_cost_usd: float = Field(ge=0)
    provisioned_concurrency_cost_usd: float = Field(ge=0)
    total_cost_usd: float = Field(ge=0)
    cost_per_million_requests_usd: float = Field(ge=0)


class AnalyzedConfig(BaseModel):
    """Combined latency, cost, and SLO analysis for one Lambda configuration."""

    model_config = ConfigDict(frozen=True)

    config: LambdaConfig
    latency: LatencyStats
    cost: CostEstimate
    cold_start_rate: float = Field(ge=0, le=1)
    slo_passed: bool
    errors: int = Field(default=0, ge=0)
    dominated: bool = False


class Recommendation(BaseModel):
    """Optimizer recommendation and supporting decision context."""

    model_config = ConfigDict(frozen=True)

    recommended_config: LambdaConfig
    reason_summary: str = Field(min_length=1)
    rejected_reasons: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[AnalyzedConfig] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


LambdaCandidateConfig = LambdaConfig
