"""Recommendation package for SLO-aware optimizer decisions."""

from lambdaopt.recommend.architecture_recommender import (
    ARM64_COMPATIBILITY_WARNING,
    ArchitectureComparison,
    compare_architecture_pair,
    compare_architectures_by_memory,
)
from lambdaopt.recommend.pc_recommender import (
    ProvisionedConcurrencyRecommendation,
    recommend_provisioned_concurrency,
)
from lambdaopt.recommend.slo_recommender import recommend_cheapest_slo_config

__all__ = [
    "ARM64_COMPATIBILITY_WARNING",
    "ArchitectureComparison",
    "ProvisionedConcurrencyRecommendation",
    "compare_architecture_pair",
    "compare_architectures_by_memory",
    "recommend_cheapest_slo_config",
    "recommend_provisioned_concurrency",
]
