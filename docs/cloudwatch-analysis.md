# CloudWatch Analysis

LambdaOpt can analyze production CloudWatch metrics without mutating Lambda configuration.

## Metrics Used

The CloudWatch client requests Lambda metrics for a function over a selected window:

- `Invocations`
- `Duration` average
- `Duration` maximum
- `Duration` p50, p95, and p99 when percentile data is available
- `Errors`
- `Throttles`
- `ConcurrentExecutions` when available

Supported window strings include `1h`, `6h`, `24h`, `7d`, and the shorter watch-oriented windows supported by the parser.

## Analysis Signals

The analyzer computes:

- total invocations,
- observed p50/p95/p99 when available,
- average and maximum duration,
- error count and error rate,
- throttle count and throttle rate,
- concurrency peak,
- SLO status when p95 is available,
- possible over-provisioning,
- risk signals.

Risk signals include:

- p95 at or above the SLO target,
- p95 near the SLO target,
- p99 much higher than p95,
- throttles present,
- elevated error rate.

## Recommendations

CloudWatch analysis recommendations are conservative. They may suggest:

- no immediate change,
- run a benchmark before changing configuration,
- investigate errors,
- investigate throttles or concurrency settings,
- investigate cold starts when p99 is much higher than p95,
- test cheaper configurations when over-provisioning is likely.

## Limitations

CloudWatch metrics are aggregate observations. They are useful for production health, but they are not a controlled benchmark.

Important limitations:

- Duration percentile metrics may be unavailable depending on CloudWatch data and query behavior.
- CloudWatch Duration is not the same as client-observed end-to-end latency.
- Missing p95/p99 data means SLO status is uncertain.
- Errors and throttles can dominate latency symptoms and should be investigated before cost tuning.
- Low-traffic functions may have noisy percentile data.

LambdaOpt reports warnings when important metrics are unavailable or empty.
