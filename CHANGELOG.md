# Changelog

All notable changes to LambdaOpt will be documented in this file.

This project follows semantic versioning for public releases.

## Unreleased

## v0.2.1 - Guided Onboarding Beta

This release makes LambdaOpt easier for first-time users without removing advanced workflows.

### Added

- `lambdaopt start` guided first-run workflow.
- Local no-AWS demo path that creates a first optimization report with one command.
- AWS readiness onboarding path that runs safe doctor checks and prints the next recommended command.
- Optional `lambdaopt start ... --run-analyze` path for read-only CloudWatch analysis after readiness checks pass.
- CLI help grouping for Start here, Core workflows, and Advanced commands.
- Start command regression tests.

### Changed

- README and usage docs now recommend `lambdaopt start` as the primary first command.
- `lambdaopt quickstart` now points users to `start` first.
- CloudWatch analysis workflow is shared by `analyze` and `start --run-analyze`.

## v0.2.0 - Production Risk Scoring Beta

This release upgrades LambdaOpt's local optimizer from p95/cost-only recommendation toward
production-oriented SLO risk assessment.

### Added

- Production-oriented SLO risk scoring for benchmarked configs using p95, p99, errors, cold-start rate, and sample confidence.
- Risk assessment details in Markdown reports and machine-readable analyzed config output.

### Changed

- Pareto frontier marking now considers p99, errors, and cold-start rate in addition to cost and p95.
- Recommendation confidence is capped by the selected config's risk confidence.

## v0.1.0 - Production Beta

Initial production beta release for safe, SLO-aware AWS Lambda optimization workflows.

### Added

- Local SLO optimizer with latency statistics, p95/p99 evaluation, SLO violation rate, cost estimation, Pareto frontier marking, and cheapest safe recommendation.
- Typed Pydantic models for Lambda configs, benchmark results, latency stats, cost estimates, analyzed configs, and recommendations.
- Synthetic simulator for CPU-bound, IO-bound, and cold-start-heavy workloads.
- Benchmark report generation in Markdown and JSON, with optional cost vs p95 chart output.
- Read-only AWS Lambda planning support for current function metadata.
- Current deployed Lambda configuration benchmarking through synchronous invocation.
- Safe candidate benchmarking through separately deployed test functions from a mapping file.
- CloudWatch metrics analysis for invocations, duration, errors, throttles, concurrency, and SLO health.
- Optional CloudWatch Logs REPORT-line cold-start analysis using `Init Duration` when available.
- Provisioned concurrency, architecture, and dry-run controller recommendations.
- Optional local Streamlit dashboard for generated reports.
- Config file support, structured exceptions, logging setup, payload redaction helpers, and least-privilege IAM policy examples.
- AWS credential safety hardening for logs, reports, debug output, payload metadata, and generated JSON.
- `lambdaopt doctor` for local environment, AWS identity, Lambda metadata, CloudWatch, CloudWatch Logs, and safety readiness checks.
- `lambdaopt iam generate` for least-privilege IAM policy generation across plan, bench, tune-candidates, analyze, analyze-with-logs, and watch-dry-run modes.
- Expanded least-privilege IAM documentation, security model documentation, and first real AWS run guidance.
- Security regression tests for redaction, report payload safety, doctor output, IAM policy generation, and GitHub Actions secret references.
- GitHub Actions CI, pre-commit configuration, Ruff, mypy, pytest, and package build support.

### Safety Defaults

- No production Lambda mutation by default.
- No current command updates memory, architecture, aliases, versions, or provisioned concurrency.
- Candidate comparison uses separate test functions rather than mutating production functions.
- `watch` is a dry-run one-shot evaluation that emits recommended actions only.
- CI uses mocked/stubbed AWS calls and does not require AWS credentials.

### Known Limitations

- Benchmarking different configurations requires candidate test functions or future alias-based workflows.
- CloudWatch percentile availability can vary by metric data availability and query behavior.
- Cold-start analysis depends on CloudWatch Logs access, REPORT log availability, and log completeness.
- Cost estimates are approximate, configurable, and not a replacement for AWS billing analysis.
- Real AWS smoke tests are manual/local and are not run in CI.
- Production mutation is intentionally out of scope for this beta.
