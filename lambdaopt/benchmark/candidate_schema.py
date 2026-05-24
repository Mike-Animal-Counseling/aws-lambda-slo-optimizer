"""Candidate benchmark mapping schema and validation."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import LambdaConfig

PRODUCTION_ALIAS_NAMES = {"prod", "production", "live", "main"}
LATEST_QUALIFIER = "$LATEST"


class CandidateMapping(BaseModel):
    """One benchmark candidate pointing at a test function or non-production alias."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name: str = Field(min_length=1)
    function_ref: str = Field(min_length=1, alias="function_name")
    memory_mb: int = Field(ge=128, le=10240)
    architecture: Literal["x86_64", "arm64"]
    timeout_seconds: int | None = Field(default=None, gt=0)
    provisioned_concurrency: int = Field(default=0, ge=0)
    runtime: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_name_for_legacy_mapping(cls, data: object) -> object:
        if isinstance(data, dict) and "name" not in data:
            function_ref = data.get("function_ref") or data.get("function_name")
            if function_ref is not None:
                return {**data, "name": str(function_ref)}
        return data

    @property
    def config(self) -> LambdaConfig:
        """Return the LambdaConfig represented by this candidate."""
        return LambdaConfig(
            memory_mb=self.memory_mb,
            architecture=self.architecture,
            timeout_seconds=self.timeout_seconds,
            provisioned_concurrency=self.provisioned_concurrency,
        )

    @property
    def source_type(self) -> Literal["alias", "test_function"]:
        """Return whether the candidate points to an alias or separate function."""
        return "alias" if ":" in self.function_ref else "test_function"

    @property
    def qualifier(self) -> str | None:
        """Return function qualifier when function_ref looks like function:qualifier."""
        if ":" not in self.function_ref:
            return None
        return self.function_ref.rsplit(":", 1)[1]


class CandidateMappings(BaseModel):
    """Top-level candidate benchmark file schema."""

    model_config = ConfigDict(frozen=True)

    base_function_name: str | None = Field(default=None, min_length=1)
    notes: str | None = None
    candidates: list[CandidateMapping] = Field(min_length=1)

    @field_validator("candidates")
    @classmethod
    def _candidate_names_and_refs_must_be_unique(
        cls,
        candidates: list[CandidateMapping],
    ) -> list[CandidateMapping]:
        names = [candidate.name for candidate in candidates]
        function_refs = [candidate.function_ref for candidate in candidates]
        duplicate_names = sorted({name for name in names if names.count(name) > 1})
        duplicate_refs = sorted({ref for ref in function_refs if function_refs.count(ref) > 1})
        if duplicate_names:
            raise ValueError(f"duplicate candidate names: {', '.join(duplicate_names)}")
        if duplicate_refs:
            raise ValueError(f"duplicate function_ref values: {', '.join(duplicate_refs)}")
        return candidates


def load_candidate_mappings(
    path: Path,
    *,
    allow_production_candidate: bool = False,
) -> CandidateMappings:
    """Load and validate a candidate benchmark mapping file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LambdaOptValidationError(f"Candidate mapping file does not exist: {path}") from exc
    except OSError as exc:
        raise LambdaOptValidationError(f"Could not read candidate mapping file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LambdaOptValidationError(f"Candidate mapping file is not valid JSON: {path}") from exc

    try:
        mappings = CandidateMappings.model_validate(payload)
    except ValidationError as exc:
        raise LambdaOptValidationError(f"Candidate mapping file has invalid data: {path}") from exc

    validate_candidate_safety(
        mappings,
        allow_production_candidate=allow_production_candidate,
    )
    return mappings


def validate_candidate_safety(
    mappings: CandidateMappings,
    *,
    allow_production_candidate: bool = False,
) -> None:
    """Reject candidate references that look like production targets by default."""
    if allow_production_candidate:
        return

    risky_refs = [
        candidate.function_ref
        for candidate in mappings.candidates
        if _appears_to_reference_production(candidate)
    ]
    if risky_refs:
        refs = ", ".join(risky_refs)
        raise LambdaOptValidationError(
            "Candidate mapping appears to reference $LATEST or a production alias: "
            f"{refs}. Use non-production aliases/test functions, or pass "
            "--allow-production-candidate if you intentionally want to benchmark these targets."
        )


def candidate_validation_warnings(mappings: CandidateMappings) -> list[str]:
    """Return non-fatal validation warnings for report output."""
    warnings: list[str] = []
    if any(candidate.source_type == "alias" for candidate in mappings.candidates):
        warnings.append(
            "At least one candidate uses a Lambda alias; verify each alias points to a "
            "non-production version before benchmarking."
        )
    if mappings.notes:
        warnings.append(f"Candidate mapping notes: {mappings.notes}")
    return warnings


def _appears_to_reference_production(candidate: CandidateMapping) -> bool:
    qualifier = candidate.qualifier
    if qualifier is None:
        return False
    normalized = qualifier.strip().lower()
    return qualifier == LATEST_QUALIFIER or normalized in PRODUCTION_ALIAS_NAMES
