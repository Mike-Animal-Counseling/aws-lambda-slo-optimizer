# Usage

LambdaOpt is a CLI for SLO-aware Lambda optimization. It can run fully local simulations, analyze local benchmark files, inspect read-only AWS metadata and CloudWatch metrics, and benchmark existing Lambda functions without changing their configuration.

## Version

```bash
lambdaopt version
```

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
