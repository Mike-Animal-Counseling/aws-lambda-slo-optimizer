"""SLO-aware recommendation logic."""

from typing import Literal

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
        decision: Literal["choose", "no_safe_config"] = "choose"
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
        base_confidence, evidence_reasons = _evidence_for_passing_config(
            recommended,
            analyzed_configs,
            target_p95_ms,
        )
        confidence = min(base_confidence, risk.confidence)
        if risk.confidence < base_confidence:
            evidence_reasons.append(
                f"Risk evidence limits recommendation strength to {risk.confidence:.0%}."
            )
        evidence_reasons.append(f"Risk assessment is {risk.level} ({risk.score}/100).")
        next_step = _next_step_for_passing_config(risk.level)
    else:
        recommended = min(
            analyzed_configs,
            key=lambda config: _normalized_violation(config, target_p95_ms),
        )
        warnings = [
            "No configuration satisfied the p95 SLO without errors; "
            "recommending the closest option."
        ]
        decision = "no_safe_config"
        reason_summary = (
            f"No configuration met p95 target {target_p95_ms:g}ms. "
            f"The closest option is {_config_label(recommended)} with p95 "
            f"{recommended.latency.p95_ms:g}ms."
        )
        confidence = 0.25
        evidence_reasons = [
            "No benchmarked configuration passed the p95 SLO without errors.",
            f"Closest p95 was {recommended.latency.p95_ms:g}ms against target {target_p95_ms:g}ms.",
        ]
        next_step = (
            "Do not roll out a new config yet; benchmark more options or inspect bottlenecks."
        )

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
        decision=decision,
        reason_summary=reason_summary,
        evidence_strength=_evidence_strength(confidence),
        evidence_reasons=evidence_reasons,
        rejected_reasons=rejected_reasons,
        warnings=warnings,
        alternatives=alternatives,
        next_step=next_step,
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


def _evidence_for_passing_config(
    recommended: AnalyzedConfig,
    analyzed_configs: list[AnalyzedConfig],
    target_p95_ms: float,
) -> tuple[float, list[str]]:
    enough_samples = recommended.latency.sample_count >= 30
    evidence_reasons = [
        (
            f"{recommended.latency.sample_count} latency samples were collected."
            if enough_samples
            else f"Only {recommended.latency.sample_count} latency samples were collected."
        ),
        "Recommended configuration recorded zero errors.",
    ]
    slo_margin = max(0.0, target_p95_ms - recommended.latency.p95_ms) / target_p95_ms
    passing_configs = [
        config
        for config in analyzed_configs
        if config.latency.p95_ms <= recommended.latency.p95_ms * 1.05 and config.errors == 0
    ]
    clear_cost_winner = all(
        config == recommended or config.cost.total_cost_usd >= recommended.cost.total_cost_usd * 1.1
        for config in passing_configs
    )
    if clear_cost_winner:
        evidence_reasons.append(
            "Recommended configuration is a clear cost winner among close SLO-safe options."
        )
    else:
        evidence_reasons.append("Several close SLO-safe options have similar cost or latency.")
    evidence_reasons.append(
        f"Recommended p95 is {recommended.latency.p95_ms:g}ms ({slo_margin:.0%} below target)."
    )

    if enough_samples and clear_cost_winner:
        return 0.9, evidence_reasons
    return 0.6, evidence_reasons


def _evidence_strength(confidence: float) -> Literal["high", "medium", "low"]:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _next_step_for_passing_config(risk_level: str) -> str:
    if risk_level == "low":
        return "Validate in a sandbox or staged alias before production rollout."
    if risk_level == "medium":
        return "Run a larger benchmark and inspect p99 before rollout."
    return "Investigate risk signals before adopting this configuration."


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
