# Roadmap

LambdaOpt is a production beta. The current focus is correctness, safety, least-privilege AWS workflows, and clear recommendations before automation.

## Milestone 1: Release-Ready Foundation

Status: implemented.

- Python package metadata and console script.
- Ruff, mypy, pytest, build, CI, and pre-commit.
- Core Pydantic domain models.
- Local optimizer and reports.
- Simulator and examples.
- Safety documentation.

## Milestone 2: Local and Safe AWS Workflows

Status: implemented for production-beta workflows.

- Read-only Lambda metadata planning.
- Current deployed configuration benchmarking.
- Separate test-function candidate benchmarking.
- CloudWatch metric analysis.
- CloudWatch Logs cold-start analysis.
- Dry-run watch controller.
- Environment readiness checks with `lambdaopt doctor`.
- Least-privilege IAM policy generation with `lambdaopt iam generate`.

Remaining work:

- More ergonomic candidate mapping generation.
- Better report linking between benchmark and CloudWatch analysis.
- Structured machine-readable plan output.

## Milestone 3: Richer Recommendation Policy

Planned:

- Configurable p95 and p99 SLO policies.
- Explicit confidence scoring inputs in reports.
- Region-aware pricing configuration.
- More architecture compatibility checks.
- Better low-traffic percentile handling.

## Milestone 4: Safer Change Planning

Planned:

- Dry-run change plans with explicit diffs.
- Alias-based benchmark workflows.
- Optional approval-gated mutation experiments for non-production aliases.
- Rollback guidance.
- Stronger confirmation UX for any future mutation feature.

## Milestone 5: Production Operations

Planned:

- Dashboard export.
- Scheduled analysis examples.
- Expanded GitHub release automation.
- More example IAM policy variants.
- More complete AWS integration tests with mocks and fixtures.

## Non-Goals for Now

- Automatic production mutation.
- Replacing AWS billing tools.
- Claiming exact cold-start attribution from incomplete logs.
- Hiding operational risks behind a single score.
