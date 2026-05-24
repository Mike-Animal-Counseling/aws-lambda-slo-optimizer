"""SLO-aware recommendation logic."""

from lambdaopt.analysis.risk import assess_config_risk
from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import AnalyzedConfig, Recommendation, RiskAssessment
from lambdaopt.recommend.architecture_recommender import arm64_recommendation_reason


def recommend_cheapest_slo_config(
    analyzed_configs: list[AnalyzedConfig],
    target_p95_ms: float,
) -> Recommendation:
    """Recommend the cheapest configuration that satisfies a p95 latency target."""
    if not analyzed_configs:
        raise LambdaOptValidationError("analyzed_configs must contain at least one config.")
    if target_p95_ms <= 0:
        raise LambdaOptValidationError("target_p95_ms must be positive.")

    passing_configs = [
        config
        for config in analyzed_configs
        if config.latency.p95_ms <= target_p95_ms and config.errors == 0
    ]

    if passing_configs:
        recommended = min(passing_configs, key=lambda config: config.cost.total_cost_usd)
        warnings: list[str] = []
        reason_summary = _passing_reason_summary(recommended, target_p95_ms)
        architecture_reason, architecture_warnings = _architecture_reason(
            recommended,
            analyzed_configs,
            target_p95_ms,
        )
        risk = _risk_for_config(recommended, target_p95_ms)
        if architecture_reason:
            reason_summary = f"{reason_summary} {architecture_reason}"
        reason_summary = f"{reason_summary} Risk level is {risk.level} ({risk.score}/100)."
        warnings.extend(architecture_warnings)
        if risk.level == "high":
            warnings.append("Recommended configuration has high production risk signals.")
        elif risk.level == "medium":
            warnings.append("Recommended configuration has medium production risk signals.")
        confidence = min(
            _confidence_for_passing_config(recommended, analyzed_configs),
            risk.confidence,
        )
    else:
        recommended = min(
            analyzed_configs,
            key=lambda config: _normalized_violation(config, target_p95_ms),
        )
        warnings = [
            "No configuration satisfied the p95 SLO without errors; "
            "recommending the closest option."
        ]
        reason_summary = (
            f"No configuration met p95 target {target_p95_ms:g}ms. "
            f"The closest option is {_config_label(recommended)} with p95 "
            f"{recommended.latency.p95_ms:g}ms."
        )
        confidence = 0.25

    rejected_reasons = {
        _config_key(config): _rejected_reason(config, recommended, target_p95_ms)
        for config in analyzed_configs
        if config != recommended
    }
    alternatives = sorted(
        [config for config in analyzed_configs if config != recommended],
        key=lambda config: (config.cost.total_cost_usd, config.latency.p95_ms),
    )

    return Recommendation(
        recommended_config=recommended.config,
        reason_summary=reason_summary,
        rejected_reasons=rejected_reasons,
        warnings=warnings,
        alternatives=alternatives,
        confidence=confidence,
    )


def _passing_reason_summary(config: AnalyzedConfig, target_p95_ms: float) -> str:
    return (
        f"{_config_label(config)} is the cheapest configuration that satisfies "
        f"p95 target {target_p95_ms:g}ms at estimated monthly cost "
        f"${config.cost.total_cost_usd:.2f}."
    )


def _architecture_reason(
    recommended: AnalyzedConfig,
    analyzed_configs: list[AnalyzedConfig],
    target_p95_ms: float,
) -> tuple[str | None, list[str]]:
    if recommended.config.architecture != "arm64":
        return None, []
    return arm64_recommendation_reason(
        analyzed_configs,
        memory_mb=recommended.config.memory_mb,
        target_p95_ms=target_p95_ms,
    )


def _rejected_reason(
    config: AnalyzedConfig,
    recommended: AnalyzedConfig,
    target_p95_ms: float,
) -> str:
    label = _config_label(config)

    if config.errors > 0:
        return f"{label} rejected because it recorded {config.errors} errors."

    if config.latency.p95_ms > target_p95_ms:
        return (
            f"{label} rejected because p95 {config.latency.p95_ms:g}ms exceeds "
            f"target {target_p95_ms:g}ms."
        )

    if config.cost.total_cost_usd > recommended.cost.total_cost_usd:
        extra_cost_rate = (
            (config.cost.total_cost_usd - recommended.cost.total_cost_usd)
            / recommended.cost.total_cost_usd
            if recommended.cost.total_cost_usd > 0
            else 0
        )
        latency_improvement_ms = max(0.0, recommended.latency.p95_ms - config.latency.p95_ms)
        return (
            f"{label} rejected because it costs {extra_cost_rate:.0%} more than the "
            f"recommendation with {latency_improvement_ms:g}ms p95 latency improvement."
        )

    return f"{label} rejected because it was not the best SLO-safe cost and latency tradeoff."


def _confidence_for_passing_config(
    recommended: AnalyzedConfig,
    analyzed_configs: list[AnalyzedConfig],
) -> float:
    enough_samples = recommended.latency.sample_count >= 30
    passing_configs = [
        config
        for config in analyzed_configs
        if config.latency.p95_ms <= recommended.latency.p95_ms * 1.05 and config.errors == 0
    ]
    clear_cost_winner = all(
        config == recommended or config.cost.total_cost_usd >= recommended.cost.total_cost_usd * 1.1
        for config in passing_configs
    )

    if enough_samples and clear_cost_winner:
        return 0.9
    return 0.6


def _risk_for_config(config: AnalyzedConfig, target_p95_ms: float) -> RiskAssessment:
    return config.risk or assess_config_risk(config, target_p95_ms=target_p95_ms)


def _normalized_violation(config: AnalyzedConfig, target_p95_ms: float) -> float:
    return max(0.0, config.latency.p95_ms - target_p95_ms) / target_p95_ms


def _config_key(config: AnalyzedConfig) -> str:
    return (
        f"{config.config.memory_mb}mb-{config.config.architecture}-"
        f"pc{config.config.provisioned_concurrency}"
    )


def _config_label(config: AnalyzedConfig) -> str:
    return f"{config.config.memory_mb}MB {config.config.architecture}"
