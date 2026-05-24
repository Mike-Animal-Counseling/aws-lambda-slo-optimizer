# Usage

LambdaOpt is a CLI for SLO-aware Lambda optimization. It can run fully local simulations, analyze local benchmark files, inspect read-only AWS metadata and CloudWatch metrics, and benchmark existing Lambda functions without changing their configuration.

## Version

```bash
lambdaopt version
```

## Quickstart

If you are not sure where to start, run:

```bash
lambdaopt quickstart
```

This prints the shortest safe path for local-only use first, then AWS commands for a sandbox or
non-production Lambda. It does not call AWS and does not mutate anything.

## Simulate

Use simulation when you want to demonstrate the optimizer without AWS credentials:

```bash
lambdaopt simulate --workload cpu-bound --p95 500 --monthly-requests 1000000 --output reports/cpu
lambdaopt simulate --workload io-bound --p95 500 --monthly-requests 1000000 --output reports/io
lambdaopt simulate --workload cold-start-heavy --p95 500 --monthly-requests 1000000 --output reports/cold
```

## Tune from Local Benchmark Results

```bash
lambdaopt tune --input examples/sample_results.json --p95 500 --monthly-requests 1000000 --output reports/sample
```

This writes:

- `benchmark_results.json`
- `recommended_config.json`
- `optimization_report.md`
- `cost_vs_p95.png` when matplotlib is available

## Tune Separate Candidate Test Functions

Use a mapping file when each candidate configuration is deployed as its own test function:

```bash
lambdaopt tune --candidates examples/candidate_functions.json --p95 500 --monthly-requests 1000000 --trials 30 --output reports/candidates
```

LambdaOpt invokes the mapped test functions and does not mutate production function configuration.

## Plan

Inspect current Lambda metadata and generate a safe benchmark plan:

```bash
lambdaopt plan my-function --p95 500 --region us-east-1 --profile default
```

This command reads metadata only. It does not update memory, architecture, aliases, versions, or provisioned concurrency.

## Bench Current Configuration

Benchmark the currently deployed configuration:

```bash
lambdaopt bench my-function --trials 50 --payload examples/payload.json --region us-east-1 --output reports/bench-current
```

This measures client-observed latency for the current function. It does not compare memory sizes unless you provide separate candidate test functions through `tune --candidates`.

## Analyze CloudWatch

Analyze production metrics without mutation:

```bash
lambdaopt analyze my-function --window 24h --p95 500 --region us-east-1 --monthly-requests 1000000 --output reports/analyze
```

Include CloudWatch Logs REPORT-line cold-start analysis:

```bash
lambdaopt analyze my-function --window 24h --p95 500 --region us-east-1 --include-logs --output reports/analyze
```

## Watch Dry-Run

Run a one-shot controller evaluation:

```bash
lambdaopt watch my-function --p95 500 --window 15m --dry-run --region us-east-1
```

The watch controller only recommends test actions. It never outputs direct mutation actions.

## Doctor

Check local environment readiness without AWS:

```bash
lambdaopt doctor
```

Check AWS identity, Lambda metadata access, CloudWatch metrics access, and optional Logs access:

```bash
lambdaopt doctor my-function --region us-east-1 --profile dev
lambdaopt doctor my-function --region us-east-1 --include-logs
lambdaopt doctor my-function --region us-east-1 --json
```

`doctor` does not invoke Lambda and does not mutate AWS resources. It never prints AWS access keys, secret keys, session tokens, or raw environment variables.

## Generate IAM Policies

Generate least-privilege policy JSON for a LambdaOpt usage mode:

```bash
lambdaopt iam generate --mode plan --function my-function --region us-east-1 --account-id 123456789012
lambdaopt iam generate --mode bench --function my-function --region us-east-1 --account-id 123456789012
lambdaopt iam generate --mode analyze-with-logs --function my-function --region us-east-1 --account-id 123456789012 --output policy.json
```

If `--account-id` is omitted, LambdaOpt uses STS `GetCallerIdentity` through the standard boto3 provider chain to infer it:

```bash
lambdaopt iam generate --mode analyze --function my-function --region us-east-1 --profile dev
```

The generated policies do not include `AdministratorAccess` or Lambda mutation actions. See [IAM Permissions](iam-permissions.md) for the full matrix.

## First Real AWS Run

Start with a sandbox account or non-production Lambda function.

Step 1: check readiness.

```bash
lambdaopt doctor my-function --region us-east-1
```

Step 2: generate least-privilege IAM policy JSON.

```bash
lambdaopt iam generate --mode analyze-with-logs --function my-function --region us-east-1 --account-id ACCOUNT_ID
```

Step 3: read Lambda metadata and print a safe benchmark plan.

```bash
lambdaopt plan my-function --p95 500 --region us-east-1
```

Step 4: analyze CloudWatch metrics without mutation.

```bash
lambdaopt analyze my-function --window 24h --p95 500
```

## Configuration

Global options:

```bash
lambdaopt --config lambdaopt.yaml --verbose tune --input examples/sample_results.json --p95 500 --monthly-requests 1000000 --output reports/sample
lambdaopt --debug analyze my-function --window 24h --p95 500 --region us-east-1
```

Example `lambdaopt.yaml`:

```yaml
default_region: us-east-1
default_profile: default
default_monthly_requests: 1000000
default_memory_sizes: [512, 1024, 1536, 2048]
default_architectures: [x86_64, arm64]
report_output_dir: reports
safety:
  allow_production_mutation: false
  require_confirmation: true
```
