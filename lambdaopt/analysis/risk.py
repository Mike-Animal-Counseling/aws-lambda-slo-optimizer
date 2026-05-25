"""Production-oriented SLO risk scoring for analyzed Lambda configurations."""

from typing import Literal

from lambdaopt.exceptions import LambdaOptValidationError
from lambdaopt.models import AnalyzedConfig, RiskAssessment

LOW_SAMPLE_THRESHOLD = 30
MEDIUM_SAMPLE_THRESHOLD = 100
P95_NEAR_SLO_RATIO = 0.9
P99_RISK_RATIO = 1.25
HIGH_COLD_START_RATE = 0.05
MEDIUM_COLD_START_RATE = 0.02


def assess_config_risk(
    config: AnalyzedConfig,
    *,
    target_p95_ms: float,
    target_p99_ms: float | None = None,
) -> RiskAssessment:
    """Assess production risk from latency, errors, cold starts, and sample evidence."""
    if target_p95_ms <= 0:
        raise LambdaOptValidationError("target_p95_ms must be positive.")
    if target_p99_ms is not None and target_p99_ms <= 0:
        raise LambdaOptValidationError("target_p99_ms must be positive when provided.")

    score = 0
    reasons: list[str] = []
    next_actions: list[str] = []

    if config.errors > 0:
        score += 35
        reasons.append(f"{config.errors} benchmark errors were observed.")
        next_actions.append("Investigate benchmark errors before optimizing cost or memory.")

    if config.latency.p95_ms > target_p95_ms:
        score += 35
        reasons.append(f"p95 {config.latency.p95_ms:g}ms exceeds target {target_p95_ms:g}ms.")
        next_actions.append("Run benchmark candidates with more memory or lower tail latency risk.")
    elif config.latency.p95_ms >= target_p95_ms * P95_NEAR_SLO_RATIO:
        score += 15
        reasons.append(f"p95 {config.latency.p95_ms:g}ms is close to target {target_p95_ms:g}ms.")
        next_actions.append("Increase sample count or compare against CloudWatch before rollout.")

    p99_target = target_p99_ms or target_p95_ms * P99_RISK_RATIO
    if config.latency.p99_ms > p99_target:
        score += 20
        reasons.append(
            f"p99 {config.latency.p99_ms:g}ms exceeds tail-risk threshold {p99_target:g}ms."
        )
        next_actions.append("Investigate cold starts or p99-heavy execution paths.")

    if config.cold_start_rate >= HIGH_COLD_START_RATE:
        score += 20
        reasons.append(f"Cold start rate {config.cold_start_rate:.1%} is high.")
        next_actions.append("Consider testing provisioned concurrency for peak windows.")
    elif config.cold_start_rate >= MEDIUM_COLD_START_RATE:
        score += 10
        reasons.append(f"Cold start rate {config.cold_start_rate:.1%} is noticeable.")
        next_actions.append("Review CloudWatch Logs Init Duration before production changes.")

    confidence = _sample_confidence(config.latency.sample_count)
    if confidence < 0.7:
        score += 10
        reasons.append(f"Only {config.latency.sample_count} latency samples were collected.")
        next_actions.append("Run a larger benchmark before trusting the recommendation.")

    normalized_score = min(score, 100)
    if not reasons:
        reasons.append("p95, p99, errors, cold starts, and sample count look acceptable.")
        next_actions.append("Compare with CloudWatch production metrics before rollout.")

    return RiskAssessment(
        score=normalized_score,
        level=_risk_level(normalized_score),
        confidence=confidence,
        reasons=reasons,
        next_actions=_dedupe(next_actions),
    )


def _sample_confidence(sample_count: int) -> float:
    if sample_count < LOW_SAMPLE_THRESHOLD:
        return 0.4
    if sample_count < MEDIUM_SAMPLE_THRESHOLD:
        return 0.7
    return 0.9


def _risk_level(score: int) -> Literal["low", "medium", "high"]:
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
