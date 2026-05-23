"""Generate safe candidate Lambda configurations for benchmark planning."""

from typing import Literal

from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import LambdaConfig

DEFAULT_MEMORY_SIZES_MB = [512, 1024, 1536, 2048]
DEFAULT_ARCHITECTURES: list[Literal["x86_64", "arm64"]] = ["x86_64", "arm64"]
DEFAULT_PROVISIONED_CONCURRENCY_OPTIONS = [0]
MIN_LAMBDA_MEMORY_MB = 128
MAX_LAMBDA_MEMORY_MB = 10240


def generate_candidate_configs(
    *,
    current_config: LambdaConfig,
    memory_sizes: list[int] | None = None,
    architectures: list[Literal["x86_64", "arm64"]] | None = None,
    include_current_config: bool = True,
    provisioned_concurrency_options: list[int] | None = None,
) -> list[LambdaConfig]:
    """Generate candidate configs without mutating any Lambda function."""
    selected_memory_sizes = memory_sizes or DEFAULT_MEMORY_SIZES_MB
    selected_architectures = architectures or DEFAULT_ARCHITECTURES
    selected_pc_options = provisioned_concurrency_options or DEFAULT_PROVISIONED_CONCURRENCY_OPTIONS

    _validate_memory_sizes(selected_memory_sizes)
    _validate_provisioned_concurrency_options(selected_pc_options)

    candidates: list[LambdaConfig] = []
    if include_current_config:
        candidates.append(current_config)

    for memory_mb in selected_memory_sizes:
        for architecture in selected_architectures:
            for provisioned_concurrency in selected_pc_options:
                candidates.append(
                    LambdaConfig(
                        memory_mb=memory_mb,
                        architecture=architecture,
                        timeout_seconds=current_config.timeout_seconds,
                        provisioned_concurrency=provisioned_concurrency,
                    )
                )

    return _deduplicate_configs(candidates)


def _validate_memory_sizes(memory_sizes: list[int]) -> None:
    for memory_mb in memory_sizes:
        if memory_mb < MIN_LAMBDA_MEMORY_MB or memory_mb > MAX_LAMBDA_MEMORY_MB:
            raise LambdaOptValidationError(
                "memory sizes must be between "
                f"{MIN_LAMBDA_MEMORY_MB} and {MAX_LAMBDA_MEMORY_MB} MB."
            )


def _validate_provisioned_concurrency_options(options: list[int]) -> None:
    for option in options:
        if option < 0:
            raise LambdaOptValidationError(
                "provisioned concurrency options must be non-negative."
            )


def _deduplicate_configs(configs: list[LambdaConfig]) -> list[LambdaConfig]:
    unique_configs: list[LambdaConfig] = []
    seen: set[tuple[int, str, int, int | None]] = set()
    for config in configs:
        key = (
            config.memory_mb,
            config.architecture,
            config.provisioned_concurrency,
            config.timeout_seconds,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_configs.append(config)

    return unique_configs
