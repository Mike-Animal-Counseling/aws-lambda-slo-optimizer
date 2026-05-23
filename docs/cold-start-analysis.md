# Cold Start Analysis

LambdaOpt can use CloudWatch Logs REPORT lines to estimate cold-start impact when log access is available.

## AWS Log Signal

Lambda REPORT log lines may include `Init Duration`. When present, it indicates initialization time for an invocation and is a practical signal for cold starts.

Example shape:

```text
REPORT RequestId: ... Duration: 120.00 ms Billed Duration: 121 ms Memory Size: 1024 MB Max Memory Used: 200 MB Init Duration: 350.00 ms
```

LambdaOpt parses:

- `Duration`
- `Billed Duration`
- `Memory Size`
- `Max Memory Used`
- `Init Duration` when present

## Computed Fields

Cold-start analysis computes:

- total parseable REPORT lines,
- cold-start count,
- cold-start rate,
- average init duration,
- p95 init duration,
- p99 init duration,
- contribution signal,
- diagnosis,
- recommendations,
- warnings.

## Diagnosis Rules

The diagnosis is intentionally heuristic:

- High cold-start rate plus a large p99/p95 gap suggests cold-start-driven tail latency.
- Low cold-start rate plus elevated p95 suggests execution-performance-driven latency is more likely.
- Missing logs or incomplete percentile context produces an inconclusive result.

When cold starts appear to drive p99 risk, LambdaOpt may recommend testing provisioned concurrency. It does not enable provisioned concurrency automatically.

## Limitations

Cold-start analysis depends on available logs.

Important limitations:

- Log retention may exclude the relevant window.
- Permissions may prevent reading logs.
- Not every log message is a REPORT line.
- Some REPORT lines may omit `Init Duration`.
- The observed log sample may be incomplete.
- LambdaOpt cannot claim an exact cold-start rate when logs are missing or incomplete.

Reports include warnings when logs are missing, unparseable, or incomplete.
