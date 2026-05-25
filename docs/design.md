# Design

LambdaOpt is designed around a conservative decision model: find low-cost configurations that satisfy latency SLOs, but avoid recommending direct production mutation.

## SLO Recommender

The SLO recommender works on analyzed benchmark configurations.

Inputs include:

- Lambda memory and architecture.
- p95 latency and other latency statistics.
- estimated monthly cost.
- error count when available.
- cold-start rate when available.
- Pareto frontier status.

The primary path is:

1. Filter configurations where p95 is at or below the target and errors are zero.
2. Pick the lowest total monthly cost among passing configurations.
3. Explain why other configurations were rejected.
4. Assign evidence strength based on sample quality and whether a clear passing winner exists.

When no configuration passes the SLO, the recommender selects the least-bad option by normalized p95 violation and emits a low-evidence warning. This is a diagnostic recommendation, not a production rollout instruction.

## Pareto Frontier

Pareto analysis marks configurations as dominated when another configuration is no worse across
the production signals LambdaOpt can compare locally:

- cost less than or equal to the current configuration,
- p95 less than or equal to the current configuration,
- p99 less than or equal to the current configuration,
- error count less than or equal to the current configuration,
- cold-start rate less than or equal to the current configuration,
- at least one dimension strictly better.

Dominated configurations are usually poor deployment candidates because another measured option is
no worse on cost, latency, and basic production risk signals.

## SLO Risk Score

LambdaOpt assigns a local, deterministic risk assessment to analyzed benchmark configs. The score
is not a black-box model. It is a transparent rule-based summary of:

- p95 SLO pass/fail and whether p95 is close to the target,
- p99 tail-latency risk,
- benchmark errors,
- cold-start rate,
- latency sample count.

The risk score influences recommendation evidence strength and adds concrete next actions such as
collecting more samples, investigating cold starts, or testing provisioned concurrency. It does not
authorize production mutation.

## Cost Model

The cost model estimates:

- request cost,
- on-demand compute cost,
- provisioned concurrency capacity cost,
- provisioned concurrency execution cost when applicable.

By default, the model excludes free-tier discounts so candidate comparisons stay clear and stable. Rates are configurable through function arguments and `lambdaopt.yaml`.

## Controller

The watch controller is a one-shot dry-run evaluator. It maps observed production signals to safe next actions.

Examples:

- High error rate: freeze optimization.
- Throttles present: investigate throttles before memory tuning.
- p95 far below SLO with low errors and low cold-start rate: test downscaling, not direct downscale.
- p95 above SLO with high cold-start rate: test provisioned concurrency.
- p95 above SLO with low cold-start rate: run benchmark or test memory increase.

The controller does not output direct mutation actions.

## Architecture Recommendation

Architecture comparison groups analyzed configs by memory size and compares `x86_64` and `arm64` when both are present. It considers latency difference, cost difference, and SLO status.

LambdaOpt always includes a compatibility warning for arm64 because native dependencies, compiled packages, Lambda layers, and container images must be validated before switching architecture.

## Provisioned Concurrency Recommendation

Provisioned concurrency recommendations are based on cold-start rate, p95/p99 behavior, request volume, estimated cost impact, and peak-hour assumptions.

The recommender prefers testing provisioned concurrency during peak windows over assuming always-on capacity is cost-effective. Low traffic workloads may receive warnings when provisioned concurrency cost dominates invocation cost.
