# Cost Model

LambdaOpt includes a local Lambda cost model for comparing candidate configurations. It is intended for decision support, not billing reconciliation.

## Components

The model estimates:

- request cost,
- on-demand compute cost,
- provisioned concurrency capacity cost,
- provisioned concurrency execution cost when provisioned concurrency is enabled,
- total monthly cost,
- cost per million requests.

## Default Assumptions

Current defaults are intentionally simple:

- Request cost: `$0.20` per 1 million requests.
- x86 compute: `$0.0000166667` per GB-second.
- arm64 compute: lower than x86 by default.
- Provisioned concurrency capacity: configurable GB-second rate.
- Provisioned concurrency execution: configurable GB-second rate.
- AWS free tier is excluded by default for clearer configuration comparisons.

The model multiplies memory in GB by duration in seconds and monthly requests to estimate GB-seconds.

## Provisioned Concurrency

Provisioned concurrency has a separate capacity cost because capacity runs for the configured concurrency, memory size, and active hours. LambdaOpt models that separately from invocation request cost and execution cost.

This matters because provisioned concurrency can reduce cold-start latency but may be expensive if enabled all the time, especially for low-traffic functions.

## Configuration

Cost rates can be supplied in `lambdaopt.yaml`:

```yaml
cost_rates:
  request_cost_per_million_usd: 0.20
  x86_compute_cost_per_gb_second_usd: 0.0000166667
  arm64_compute_cost_per_gb_second_usd: 0.0000133334
  provisioned_concurrency_cost_per_gb_second_usd: 0.0000041667
  provisioned_concurrency_execution_cost_per_gb_second_usd: 0.0000166667
```

## Limitations

The model does not currently account for every account-specific or region-specific billing detail.

Examples not fully modeled:

- regional price variation,
- Compute Savings Plans,
- account discounts,
- free-tier sharing across functions,
- data transfer,
- downstream service cost,
- retry amplification,
- asynchronous event source behavior.

Use LambdaOpt cost estimates for relative comparison between candidate Lambda configurations, then validate final decisions against AWS pricing and account billing context.
