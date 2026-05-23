"""Local AWS Lambda cost estimation model."""

from typing import Literal

from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import CostEstimate

DEFAULT_REQUEST_COST_PER_MILLION_USD = 0.20
DEFAULT_X86_COMPUTE_COST_PER_GB_SECOND_USD = 0.0000166667
DEFAULT_ARM64_COMPUTE_COST_PER_GB_SECOND_USD = 0.0000133334
DEFAULT_PROVISIONED_CONCURRENCY_COST_PER_GB_SECOND_USD = 0.0000041667
DEFAULT_PROVISIONED_CONCURRENCY_EXECUTION_COST_PER_GB_SECOND_USD = 0.0000166667
FREE_TIER_REQUESTS = 1_000_000
FREE_TIER_GB_SECONDS = 400_000.0


def estimate_lambda_cost(
    *,
    memory_mb: int,
    avg_duration_ms: float,
    monthly_requests: int,
    architecture: Literal["x86_64", "arm64"],
    provisioned_concurrency: int = 0,
    provisioned_concurrency_hours: float = 0,
    include_free_tier: bool = False,
    request_cost_per_million_usd: float = DEFAULT_REQUEST_COST_PER_MILLION_USD,
    x86_compute_cost_per_gb_second_usd: float = DEFAULT_X86_COMPUTE_COST_PER_GB_SECOND_USD,
    arm64_compute_cost_per_gb_second_usd: float = DEFAULT_ARM64_COMPUTE_COST_PER_GB_SECOND_USD,
    provisioned_concurrency_cost_per_gb_second_usd: float = (
        DEFAULT_PROVISIONED_CONCURRENCY_COST_PER_GB_SECOND_USD
    ),
    provisioned_concurrency_execution_cost_per_gb_second_usd: float = (
        DEFAULT_PROVISIONED_CONCURRENCY_EXECUTION_COST_PER_GB_SECOND_USD
    ),
) -> CostEstimate:
    """Estimate monthly Lambda request, compute, and provisioned concurrency cost.

    Assumptions:
    - Request pricing is modeled as a flat per-million request charge.
    - On-demand execution uses architecture-specific GB-second rates.
    - Provisioned concurrency capacity is billed continuously for the configured
      provisioned concurrency, memory, and active hours.
    - When provisioned concurrency is enabled, execution GB-seconds use the
      provisioned-concurrency execution rate and capacity is added separately.
    - The AWS free tier is excluded by default for clearer config comparisons.
    """
    _validate_cost_inputs(
        memory_mb=memory_mb,
        avg_duration_ms=avg_duration_ms,
        monthly_requests=monthly_requests,
        provisioned_concurrency=provisioned_concurrency,
        provisioned_concurrency_hours=provisioned_concurrency_hours,
    )

    memory_gb = memory_mb / 1024
    gb_seconds = memory_gb * (avg_duration_ms / 1000) * monthly_requests

    billable_requests = monthly_requests
    billable_gb_seconds = gb_seconds
    if include_free_tier:
        billable_requests = max(0, monthly_requests - FREE_TIER_REQUESTS)
        billable_gb_seconds = max(0.0, gb_seconds - FREE_TIER_GB_SECONDS)

    request_cost_usd = (billable_requests / 1_000_000) * request_cost_per_million_usd
    compute_rate = _compute_rate_for_architecture(
        architecture=architecture,
        x86_compute_cost_per_gb_second_usd=x86_compute_cost_per_gb_second_usd,
        arm64_compute_cost_per_gb_second_usd=arm64_compute_cost_per_gb_second_usd,
    )
    execution_rate = (
        provisioned_concurrency_execution_cost_per_gb_second_usd
        if provisioned_concurrency > 0
        else compute_rate
    )
    compute_cost_usd = billable_gb_seconds * execution_rate

    provisioned_concurrency_gb_seconds = (
        memory_gb * provisioned_concurrency * provisioned_concurrency_hours * 3600
    )
    provisioned_concurrency_cost_usd = (
        provisioned_concurrency_gb_seconds * provisioned_concurrency_cost_per_gb_second_usd
    )
    total_cost_usd = request_cost_usd + compute_cost_usd + provisioned_concurrency_cost_usd
    cost_per_million_requests_usd = (
        (total_cost_usd / monthly_requests) * 1_000_000 if monthly_requests > 0 else 0.0
    )

    return CostEstimate(
        monthly_requests=monthly_requests,
        request_cost_usd=request_cost_usd,
        compute_cost_usd=compute_cost_usd,
        provisioned_concurrency_cost_usd=provisioned_concurrency_cost_usd,
        total_cost_usd=total_cost_usd,
        cost_per_million_requests_usd=cost_per_million_requests_usd,
    )


def _compute_rate_for_architecture(
    *,
    architecture: Literal["x86_64", "arm64"],
    x86_compute_cost_per_gb_second_usd: float,
    arm64_compute_cost_per_gb_second_usd: float,
) -> float:
    if architecture == "x86_64":
        return x86_compute_cost_per_gb_second_usd
    if architecture == "arm64":
        return arm64_compute_cost_per_gb_second_usd
    raise LambdaOptValidationError(f"Unsupported architecture: {architecture}")


def _validate_cost_inputs(
    *,
    memory_mb: int,
    avg_duration_ms: float,
    monthly_requests: int,
    provisioned_concurrency: int,
    provisioned_concurrency_hours: float,
) -> None:
    if memory_mb < 128 or memory_mb > 10240:
        raise LambdaOptValidationError("memory_mb must be between 128 and 10240.")
    if avg_duration_ms < 0:
        raise LambdaOptValidationError("avg_duration_ms must be non-negative.")
    if monthly_requests < 0:
        raise LambdaOptValidationError("monthly_requests must be non-negative.")
    if provisioned_concurrency < 0:
        raise LambdaOptValidationError("provisioned_concurrency must be non-negative.")
    if provisioned_concurrency_hours < 0:
        raise LambdaOptValidationError("provisioned_concurrency_hours must be non-negative.")
