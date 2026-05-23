"""Machine-readable JSON report writers."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from lambdaopt.models import AnalyzedConfig, Recommendation

BENCHMARK_RESULTS_FILENAME = "benchmark_results.json"
RECOMMENDED_CONFIG_FILENAME = "recommended_config.json"


def write_benchmark_results_json(
    analyzed_configs: list[AnalyzedConfig],
    output_dir: Path,
) -> Path:
    """Write analyzed benchmark results as stable JSON."""
    path = output_dir / BENCHMARK_RESULTS_FILENAME
    _write_json(path, {"results": analyzed_configs})
    return path


def write_recommendation_json(recommendation: Recommendation, output_dir: Path) -> Path:
    """Write the selected recommendation as stable JSON."""
    path = output_dir / RECOMMENDED_CONFIG_FILENAME
    _write_json(path, recommendation)
    return path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_to_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value
