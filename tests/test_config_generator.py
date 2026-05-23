import pytest

from lambdaopt.benchmark.config_generator import generate_candidate_configs
from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import LambdaConfig


def test_generate_candidate_configs_uses_defaults() -> None:
    current = LambdaConfig(memory_mb=1024, architecture="arm64", timeout_seconds=10)

    candidates = generate_candidate_configs(current_config=current)

    assert len(candidates) == 8
    assert LambdaConfig(memory_mb=512, architecture="x86_64", timeout_seconds=10) in candidates
    assert LambdaConfig(memory_mb=2048, architecture="arm64", timeout_seconds=10) in candidates


def test_generate_candidate_configs_includes_current_config_outside_defaults() -> None:
    current = LambdaConfig(memory_mb=3008, architecture="x86_64", timeout_seconds=15)

    candidates = generate_candidate_configs(current_config=current)

    assert candidates[0] == current
    assert current in candidates
    assert len(candidates) == 9


def test_generate_candidate_configs_can_exclude_current_config() -> None:
    current = LambdaConfig(memory_mb=3008, architecture="x86_64", timeout_seconds=15)

    candidates = generate_candidate_configs(
        current_config=current,
        include_current_config=False,
    )

    assert current not in candidates
    assert len(candidates) == 8


def test_generate_candidate_configs_validates_memory_range() -> None:
    current = LambdaConfig(memory_mb=1024, architecture="arm64")

    with pytest.raises(LambdaOptValidationError):
        generate_candidate_configs(current_config=current, memory_sizes=[64])


def test_generate_candidate_configs_supports_provisioned_concurrency_options() -> None:
    current = LambdaConfig(memory_mb=1024, architecture="arm64")

    candidates = generate_candidate_configs(
        current_config=current,
        memory_sizes=[1024],
        architectures=["arm64"],
        include_current_config=False,
        provisioned_concurrency_options=[0, 2],
    )

    assert [candidate.provisioned_concurrency for candidate in candidates] == [0, 2]
