# AWS Smoke Test

This guide validates LambdaOpt against a minimal non-production Lambda function.

Use a sandbox AWS account or a clearly non-production Lambda function. Do not use a production function for your first smoke test. LambdaOpt does not need administrator permissions. Benchmark commands invoke the function and may incur small AWS costs.

## Prerequisites

- Python 3.11 or newer.
- LambdaOpt installed locally:

```bash
python -m pip install -e ".[dev,aws,charts]"
```

- AWS CLI installed and configured.
- A sandbox AWS account or non-production AWS environment.
- A test Lambda function in the target region.
- Least-privilege IAM permissions for the commands you want to run.

Confirm your AWS identity:

```bash
aws sts get-caller-identity
```

## Permissions

Start with least privilege. Do not use `AdministratorAccess`.

For `plan` and `analyze`, see:

```text
examples/iam/lambdaopt-readonly-policy.json
```

For `bench`, see:

```text
examples/iam/lambdaopt-benchmark-policy.json
```

For `analyze --include-logs`, see:

```text
examples/iam/lambdaopt-analyze-with-logs-policy.json
```

Replace `REGION`, `ACCOUNT_ID`, `FUNCTION_NAME`, and `LOG_GROUP_NAME` before attaching any policy. See [IAM Permissions](iam-permissions.md) for the command-by-command matrix.

## Create or Select a Test Lambda

You can use an existing non-production Lambda or deploy the example in `examples/aws-smoke-test`.

The example handler is intentionally small and deterministic. It accepts a JSON event and returns a simple response. Use the included `event.json` as the benchmark payload.

If you deploy manually, create a Python Lambda function named `my-test-function` in `us-east-1` with handler:

```text
handler.handler
```

After deployment, invoke it once so CloudWatch Logs and metrics have data:

```bash
aws lambda invoke \
  --function-name my-test-function \
  --region us-east-1 \
  --payload fileb://examples/aws-smoke-test/event.json \
  response.json
```

## Run LambdaOpt Plan

Read current Lambda metadata and generate a benchmark plan:

```bash
lambdaopt plan my-test-function --region us-east-1 --p95 500
```

Expected output shape:

```text
Benchmark plan for my-test-function
Target p95: 500 ms
Region: us-east-1
Current config: 512MB x86_64, timeout 30s, provisioned concurrency 0
Safety notes:
  - LambdaOpt only reads Lambda metadata while creating a plan.
  - No production Lambda configuration will be changed.
```

## Run LambdaOpt Bench

Benchmark the currently deployed configuration:

```bash
lambdaopt bench my-test-function \
  --trials 20 \
  --payload examples/aws-smoke-test/event.json \
  --region us-east-1 \
  --p95 500 \
  --output reports/smoke
```

Expected output shape:

```text
Benchmarked current deployed config only; no memory or architecture comparison was performed.
Recommendation: 512MB x86_64 for p95 <= 500ms (60% confidence).
Reports written to reports/smoke
```

This command invokes the Lambda function 20 measured times, plus any warmup invocations you request. It does not change memory or architecture.

## Run CloudWatch Analyze

Analyze recent CloudWatch metrics:

```bash
lambdaopt analyze my-test-function \
  --window 1h \
  --p95 500 \
  --region us-east-1 \
  --output reports/analyze
```

Expected output shape:

```text
Analyzed CloudWatch metrics for my-test-function over 1h.
SLO health: healthy
Reports written to reports/analyze
```

If p95 percentile data is unavailable, LambdaOpt will report SLO health as unknown and include a warning in the report.

## Analyze Logs for Cold Starts

If your IAM role can read CloudWatch Logs, include REPORT log analysis:

```bash
lambdaopt analyze my-test-function \
  --window 1h \
  --p95 500 \
  --region us-east-1 \
  --include-logs \
  --output reports/analyze-logs
```

Expected output shape:

```text
Analyzed CloudWatch metrics for my-test-function over 1h.
SLO health: healthy
Reports written to reports/analyze-logs
```

The report may show cold-start rate, init duration stats, and a diagnosis when parseable REPORT lines include `Init Duration`.

## View Reports

Open generated Markdown reports:

```text
reports/smoke/optimization_report.md
reports/analyze/cloudwatch_analysis_report.md
reports/analyze-logs/cloudwatch_analysis_report.md
```

If you installed the dashboard extra:

```bash
python -m pip install -e ".[dashboard]"
lambdaopt dashboard --report reports/smoke
```

## Cleanup

If you created a dedicated smoke-test Lambda, delete it after validation:

```bash
aws lambda delete-function --function-name my-test-function --region us-east-1
```

Remove local generated files if desired:

```bash
rm -rf reports/smoke reports/analyze reports/analyze-logs response.json
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force reports\smoke, reports\analyze, reports\analyze-logs, response.json
```

Only remove resources you created for the smoke test.

## Troubleshooting

### Missing AWS Credentials

Symptom:

```text
AWS credentials were not found. Configure credentials or pass --profile.
```

Fix:

```bash
aws configure
aws sts get-caller-identity
lambdaopt plan my-test-function --region us-east-1 --profile default
```

### AccessDenied

Symptom:

```text
AWS denied read access to Lambda configuration
```

Fix: attach the least-privilege policy for the command you are running. For benchmark commands, include `lambda:InvokeFunction` on the test function ARN.

### Wrong Region

Symptom: function not found, no metrics, or no logs.

Fix: pass the region where the function is deployed:

```bash
lambdaopt plan my-test-function --region us-east-1
```

### Function Not Found

Symptom:

```text
ResourceNotFoundException
```

Fix: verify the function name and region:

```bash
aws lambda get-function --function-name my-test-function --region us-east-1
```

### No CloudWatch Metrics Yet

CloudWatch metrics may not appear immediately for a brand-new function. Invoke the function and wait a few minutes before running `analyze`.

### No Logs Found

The function may not have been invoked, log retention may have expired, or the IAM identity may lack `logs:FilterLogEvents`. Invoke the function once and verify the log group:

```bash
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/my-test-function --region us-east-1
```

### Cold-Start Logs Unavailable

Not every REPORT line includes `Init Duration`. LambdaOpt cannot claim an exact cold-start rate from incomplete logs. Use `analyze --include-logs` as a diagnostic signal, not a complete tracing system.
