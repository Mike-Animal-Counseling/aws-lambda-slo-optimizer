"""Read-only benchmark planning models and helpers."""

from pydantic import BaseModel, ConfigDict, Field

from lambdaopt.benchmark.config_generator import generate_candidate_configs
from lambdaopt.models import LambdaConfig

DEFAULT_ESTIMATED_INVOCATIONS = 100
NO_MUTATION_SAFETY_NOTE = (
    "Safety: this plan is read-only; no production config will be changed. "
    "LambdaOpt only reads Lambda metadata while creating a plan."
)


class BenchmarkPlan(BaseModel):
    """A read-only plan for candidate Lambda benchmark configurations."""

    model_config = ConfigDict(frozen=True)

    function_name: str = Field(min_length=1)
    current_config: LambdaConfig
    candidate_configs: list[LambdaConfig] = Field(min_length=1)
    estimated_invocations: int = Field(ge=0)
    safety_notes: list[str] = Field(min_length=1)


def create_benchmark_plan(
    *,
    function_name: str,
    current_config: LambdaConfig,
    estimated_invocations: int = DEFAULT_ESTIMATED_INVOCATIONS,
    candidate_configs: list[LambdaConfig] | None = None,
    safety_notes: list[str] | None = None,
) -> BenchmarkPlan:
    """Create a read-only benchmark plan from the current Lambda configuration."""
    candidates = candidate_configs or generate_candidate_configs(current_config=current_config)
    notes = safety_notes or [
        NO_MUTATION_SAFETY_NOTE,
        "Suggested next command: lambdaopt benchmark is planned for a future release.",
    ]

    return BenchmarkPlan(
        function_name=function_name,
        current_config=current_config,
        candidate_configs=candidates,
        estimated_invocations=estimated_invocations,
        safety_notes=notes,
    )
