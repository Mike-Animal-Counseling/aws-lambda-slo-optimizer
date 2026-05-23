# Safety

LambdaOpt is intentionally conservative. Its current AWS workflows are read-only or invoke explicitly named functions for benchmarking. It does not mutate production Lambda configuration by default.

## Mutation Policy

Current commands do not:

- update Lambda memory,
- update Lambda architecture,
- update Lambda timeout,
- update `$LATEST`,
- publish versions,
- shift aliases,
- change provisioned concurrency,
- change reserved concurrency.

Candidate benchmarking is supported through a mapping file of separate test functions. This avoids using the production function as the experiment target.

## Candidate Benchmarking

The safe candidate workflow expects a file like:

```json
{
  "candidates": [
    {
      "function_name": "my-fn-512-x86-test",
      "memory_mb": 512,
      "architecture": "x86_64"
    },
    {
      "function_name": "my-fn-1024-arm-test",
      "memory_mb": 1024,
      "architecture": "arm64"
    }
  ]
}
```

LambdaOpt invokes each named test function and uses the declared candidate config for analysis. It does not update memory or architecture during the run.

## Dry-Run Controller

`lambdaopt watch` is dry-run. It emits actions such as:

- `NO_CHANGE`
- `RUN_BENCHMARK`
- `DOWNSCALE_MEMORY_TEST`
- `UPSCALE_MEMORY_TEST`
- `SWITCH_TO_ARM64_TEST`
- `ENABLE_PROVISIONED_CONCURRENCY_TEST`
- `INVESTIGATE_ERRORS`
- `INVESTIGATE_THROTTLES`
- `FREEZE_OPTIMIZATION`

These are recommendations to test or investigate. They are not infrastructure changes.

## Guardrails

The controller prioritizes operational risk:

- High error rate freezes optimization.
- Throttles are investigated before memory optimization.
- Over-provisioning signals produce downscale tests, not direct downscales.
- Cold-start-driven SLO risk produces provisioned concurrency test recommendations.
- Near-SLO behavior can produce no-change or benchmark recommendations rather than aggressive tuning.

## Payload and Log Safety

LambdaOpt does not log raw payload contents during benchmark invocation. Security helpers redact likely sensitive keys including:

- `password`
- `token`
- `secret`
- `authorization`
- `api_key`

Reports should contain benchmark metadata and aggregate results, not full request payloads.

## AWS Error Handling

Known AWS and validation errors are summarized for CLI users. Full tracebacks are hidden by default and can be shown with `--debug` when troubleshooting.
