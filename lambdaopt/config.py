"""Application configuration and local data loading helpers."""

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from lambdaopt import __version__
from lambdaopt.analysis.cost_model import (
    DEFAULT_ARM64_COMPUTE_COST_PER_GB_SECOND_USD,
    DEFAULT_PROVISIONED_CONCURRENCY_COST_PER_GB_SECOND_USD,
    DEFAULT_PROVISIONED_CONCURRENCY_EXECUTION_COST_PER_GB_SECOND_USD,
    DEFAULT_REQUEST_COST_PER_MILLION_USD,
    DEFAULT_X86_COMPUTE_COST_PER_GB_SECOND_USD,
)
from lambdaopt.exceptions import DataLoadError, LambdaOptConfigError
from lambdaopt.models import BenchmarkResult

DEFAULT_CONFIG_FILE = Path("lambdaopt.yaml")
DEFAULT_MEMORY_SIZES = [512, 1024, 1536, 2048]
DEFAULT_ARCHITECTURES: list[Literal["x86_64", "arm64"]] = ["x86_64", "arm64"]


class CostRatesConfig(BaseModel):
    """Configurable cost rates used by local estimates."""

    request_cost_per_million_usd: float = DEFAULT_REQUEST_COST_PER_MILLION_USD
    x86_compute_cost_per_gb_second_usd: float = DEFAULT_X86_COMPUTE_COST_PER_GB_SECOND_USD
    arm64_compute_cost_per_gb_second_usd: float = DEFAULT_ARM64_COMPUTE_COST_PER_GB_SECOND_USD
    provisioned_concurrency_cost_per_gb_second_usd: float = (
        DEFAULT_PROVISIONED_CONCURRENCY_COST_PER_GB_SECOND_USD
    )
    provisioned_concurrency_execution_cost_per_gb_second_usd: float = (
        DEFAULT_PROVISIONED_CONCURRENCY_EXECUTION_COST_PER_GB_SECOND_USD
    )

    @field_validator("*")
    @classmethod
    def _rates_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("cost rates must be non-negative")
        return value


class SafetyConfig(BaseModel):
    """Safety guardrails for operations that could affect infrastructure."""

    allow_production_mutation: bool = False
    require_confirmation: bool = True


class LambdaOptConfig(BaseModel):
    """User configuration loaded from lambdaopt.yaml or an explicit path."""

    default_region: str | None = None
    default_profile: str | None = None
    default_monthly_requests: int = 1_000_000
    default_memory_sizes: list[int] = Field(default_factory=lambda: DEFAULT_MEMORY_SIZES.copy())
    default_architectures: list[Literal["x86_64", "arm64"]] = Field(
        default_factory=lambda: DEFAULT_ARCHITECTURES.copy()
    )
    cost_rates: CostRatesConfig = Field(default_factory=CostRatesConfig)
    report_output_dir: Path = Path("reports")
    safety: SafetyConfig = Field(default_factory=SafetyConfig)

    @field_validator("default_monthly_requests")
    @classmethod
    def _monthly_requests_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("default_monthly_requests must be non-negative")
        return value

    @field_validator("default_memory_sizes")
    @classmethod
    def _memory_sizes_must_be_valid(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("default_memory_sizes must contain at least one value")
        invalid = [memory for memory in value if memory < 128 or memory > 10240]
        if invalid:
            raise ValueError("default_memory_sizes must be between 128 and 10240 MB")
        return value

    @field_validator("default_architectures")
    @classmethod
    def _architectures_must_not_be_empty(
        cls,
        value: list[Literal["x86_64", "arm64"]],
    ) -> list[Literal["x86_64", "arm64"]]:
        if not value:
            raise ValueError("default_architectures must contain at least one value")
        return value


def get_version() -> str:
    """Return the current LambdaOpt package version."""
    return __version__


def load_config(path: str | Path | None = None) -> LambdaOptConfig:
    """Load LambdaOpt configuration from YAML.

    When ``path`` is omitted, ``lambdaopt.yaml`` in the current working directory
    is used if present; otherwise built-in defaults are returned.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_FILE
    if path is None and not config_path.exists():
        return LambdaOptConfig()

    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LambdaOptConfigError(f"Config file does not exist: {config_path}") from exc
    except OSError as exc:
        raise LambdaOptConfigError(f"Could not read config file: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise LambdaOptConfigError(f"Config file is not valid YAML: {config_path}") from exc

    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, dict):
        raise LambdaOptConfigError("Config file must contain a YAML mapping at the top level.")

    try:
        return LambdaOptConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise LambdaOptConfigError(f"Config file has invalid values: {config_path}") from exc


def load_benchmark_results(path: str | Path) -> list[BenchmarkResult]:
    """Load benchmark results from a local JSON file.

    The file may contain either a JSON array of ``BenchmarkResult`` objects or an
    object with a top-level ``results`` array.
    """
    source = Path(path)

    try:
        payload: object = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataLoadError(f"Benchmark results file does not exist: {source}") from exc
    except OSError as exc:
        raise DataLoadError(f"Could not read benchmark results file: {source}") from exc
    except JSONDecodeError as exc:
        raise DataLoadError(f"Benchmark results file is not valid JSON: {source}") from exc

    result_items = _extract_result_items(payload, source)

    try:
        return [BenchmarkResult.model_validate(item) for item in result_items]
    except ValidationError as exc:
        raise DataLoadError(f"Benchmark results file has invalid data: {source}") from exc


def _extract_result_items(payload: object, source: Path) -> list[Any]:
    """Return benchmark result items from a supported JSON payload shape."""
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return results

    raise DataLoadError(
        f"Benchmark results JSON must be an array or an object with a 'results' array: {source}"
    )
