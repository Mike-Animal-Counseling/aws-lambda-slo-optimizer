# Changelog

All notable changes to LambdaOpt will be documented in this file.

This project follows semantic versioning once public releases begin.

## 0.1.0 - Unreleased

### Added

- Python package scaffold with Typer CLI.
- Typed Pydantic domain models for Lambda configs, benchmark results, costs, analysis, and recommendations.
- Local SLO optimizer with latency statistics, cost estimation, Pareto frontier marking, and cheapest safe recommendation.
- Synthetic simulator for CPU-bound, IO-bound, and cold-start-heavy workloads.
- Local report generation in Markdown, JSON, and optional charts.
- Read-only AWS metadata planning.
- Current-config Lambda invocation benchmarking.
- Safe candidate benchmarking using separate mapped test functions.
- CloudWatch metrics analysis and optional CloudWatch Logs cold-start analysis.
- Provisioned concurrency, architecture, and dry-run controller recommendations.
- Config file support, logging setup, custom exceptions, and payload redaction helpers.
- Test suite, Ruff, mypy, GitHub Actions CI, and pre-commit configuration.
