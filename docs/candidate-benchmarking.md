# Candidate Benchmarking

LambdaOpt benchmarks multiple configurations safely by invoking non-production aliases or separate test functions. It does not change Lambda memory, architecture, aliases, versions, or provisioned concurrency.

## Why Aliases or Test Functions

Changing a production Lambda configuration during a benchmark can affect real traffic. LambdaOpt avoids that by requiring users to provide already-created benchmark targets:

- non-production aliases such as `my-function:test-1024-arm`,
- separate test functions such as `my-function-1024-arm-test`.

Each candidate target should already have the memory, architecture, timeout, environment, and dependencies you want to test.

## Candidate File

```json
{
  "base_function_name": "my-function",
  "notes": "All candidates point to non-production aliases or test functions.",
  "candidates": [
    {
      "name": "512MB x86 test",
      "function_ref": "my-function:test-512-x86",
      "memory_mb": 512,
      "architecture": "x86_64",
      "provisioned_concurrency": 0
    },
    {
      "name": "1024MB arm test",
      "function_ref": "my-function:test-1024-arm",
      "memory_mb": 1024,
      "architecture": "arm64",
      "provisioned_concurrency": 0
    }
  ]
}
```

See [`examples/candidates.example.json`](../examples/candidates.example.json).

## Recommended Naming

Use names that make the tested config obvious:

- `my-function:test-512-x86`
- `my-function:test-1024-arm`
- `my-function-1536-x86-test`

Avoid production-looking qualifiers such as:

- `$LATEST`
- `prod`
- `production`
- `live`
- `main`

LambdaOpt rejects those by default unless `--allow-production-candidate` is explicitly passed.

## Dry-Run Plan

Validate the candidate file and print the benchmark plan without invoking anything:

```bash
lambdaopt tune --candidates examples/candidates.example.json --p95 500 --trials 50 --output reports/candidates --dry-run-plan
```

The plan shows:

- candidate name,
- function reference,
- alias vs separate test function,
- memory,
- architecture,
- estimated invocation count,
- safety note.

## Run Benchmark

For automation or CI-like local runs, skip the interactive confirmation with `--yes`:

```bash
lambdaopt tune --candidates examples/candidates.example.json --p95 500 --trials 50 --output reports/candidates --yes
```

Without `--yes`, LambdaOpt asks for confirmation before invoking multiple candidates.

## Safety Warnings

- Candidate benchmarking invokes Lambda functions and may incur small AWS costs.
- Invocation can trigger application side effects. Use safe payloads and non-production targets.
- LambdaOpt does not mutate function configuration.
- Verify aliases point to non-production versions before benchmarking.

## Troubleshooting

### Duplicate Candidate Names

Every candidate `name` must be unique so reports are readable.

### Duplicate Function References

Every `function_ref` must be unique. If two candidates point to the same function or alias, the benchmark would compare duplicate targets.

### Invalid Memory or Architecture

Memory must be between 128 and 10240 MB. Architecture must be `x86_64` or `arm64`.

### Production Alias Rejected

If a candidate points to `$LATEST`, `prod`, `production`, `live`, or `main`, LambdaOpt rejects it by default. Create a non-production alias instead.

### AccessDenied

The caller needs `lambda:InvokeFunction` for each candidate target. See [IAM Permissions](iam-permissions.md).
