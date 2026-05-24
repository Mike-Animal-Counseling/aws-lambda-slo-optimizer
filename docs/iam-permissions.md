# IAM Permissions

LambdaOpt should be run with least-privilege IAM permissions. You should not use
`AdministratorAccess` for normal LambdaOpt workflows.

LambdaOpt is read-only by default for Lambda configuration. Some benchmark commands invoke
Lambda functions, which can execute application code and may incur small AWS costs, but the
current production-beta commands do not update memory, architecture, aliases, versions, or
provisioned concurrency.

## Generate A Policy

Use `lambdaopt iam generate` to create a scoped policy for a specific command mode:

```bash
lambdaopt iam generate \
  --mode analyze-with-logs \
  --function my-function \
  --region us-east-1 \
  --account-id 123456789012 \
  --output policy.json
```

If `--account-id` is omitted, LambdaOpt tries to infer it with `sts:GetCallerIdentity` using the
standard boto3 credential provider chain:

```bash
lambdaopt iam generate \
  --mode plan \
  --function my-function \
  --region us-east-1 \
  --profile dev
```

For machine-readable output only:

```bash
lambdaopt iam generate \
  --mode bench \
  --function my-function \
  --region us-east-1 \
  --account-id 123456789012 \
  --json-only
```

Supported modes:

- `plan`
- `bench`
- `tune-candidates`
- `analyze`
- `analyze-with-logs`
- `watch-dry-run`

## First Real AWS Run

For a first production-beta validation, use a sandbox account or non-production function:

```bash
lambdaopt doctor my-function --region us-east-1
lambdaopt iam generate --mode analyze-with-logs --function my-function --region us-east-1 --account-id ACCOUNT_ID
lambdaopt plan my-function --p95 500 --region us-east-1
lambdaopt analyze my-function --window 24h --p95 500
```

For dry-run watch with CloudWatch Logs checks:

```bash
lambdaopt iam generate \
  --mode watch-dry-run \
  --function my-function \
  --region us-east-1 \
  --account-id 123456789012 \
  --include-logs
```

## Permission Matrix

| Command or mode | Purpose | Lambda permissions | CloudWatch permissions | CloudWatch Logs permissions | Mutates AWS? | Notes |
|---|---|---|---|---|---|---|
| `lambdaopt plan` / `plan` | Read current Lambda metadata and generate a benchmark plan. | `lambda:GetFunction`, `lambda:GetFunctionConfiguration` | None | None | No | Reads metadata only. |
| `lambdaopt bench` / `bench` | Invoke a function and analyze client-observed latency. | `lambda:GetFunction`, `lambda:GetFunctionConfiguration`, `lambda:InvokeFunction` | None | None | No config mutation; invokes function | Invocation can trigger normal function side effects. Use a safe payload. |
| `lambdaopt tune --input` | Analyze local benchmark JSON. | None | None | None | No | Fully local; no AWS permissions required. |
| `lambdaopt tune --candidates` / `tune-candidates` | Invoke separate candidate test functions or aliases from a mapping file. | `lambda:GetFunction`, `lambda:GetFunctionConfiguration`, `lambda:InvokeFunction` | None | None | No config mutation; invokes functions | Scope invocation to approved test functions or aliases. |
| `lambdaopt analyze` / `analyze` | Read current config and CloudWatch production metrics. | `lambda:GetFunction`, `lambda:GetFunctionConfiguration` | `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics` | None | No | CloudWatch metric APIs generally require `Resource: "*"` in IAM. |
| `lambdaopt analyze --include-logs` / `analyze-with-logs` | Read current config, CloudWatch metrics, and REPORT logs for cold-start analysis. | `lambda:GetFunction`, `lambda:GetFunctionConfiguration` | `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics` | `logs:FilterLogEvents`, `logs:DescribeLogGroups`, `logs:DescribeLogStreams` | No | Logs are read for Lambda REPORT lines. LambdaOpt does not change log groups or retention. |
| `lambdaopt watch --dry-run` / `watch-dry-run` | Run a one-shot dry-run controller evaluation from metadata and metrics. | `lambda:GetFunction`, `lambda:GetFunctionConfiguration` | `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics` | Optional with `--include-logs` | No | Emits recommended actions only; does not execute changes. |

## Example Policy Snippets

Plan mode:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadLambdaFunctionMetadata",
      "Effect": "Allow",
      "Action": [
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration"
      ],
      "Resource": [
        "arn:aws:lambda:us-east-1:123456789012:function:my-function",
        "arn:aws:lambda:us-east-1:123456789012:function:my-function:*"
      ]
    }
  ]
}
```

Analyze with logs mode adds CloudWatch metrics and scoped log-group reads:

```json
{
  "Sid": "ReadLambdaReportLogs",
  "Effect": "Allow",
  "Action": [
    "logs:DescribeLogStreams",
    "logs:FilterLogEvents"
  ],
  "Resource": [
    "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/my-function",
    "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/my-function:*"
  ]
}
```

## Why CloudWatch Metrics Use `Resource: "*"`

CloudWatch metric read APIs such as `cloudwatch:GetMetricData` and
`cloudwatch:GetMetricStatistics` do not support Lambda function-level resource ARNs in the same
way Lambda and CloudWatch Logs actions do. LambdaOpt scopes Lambda and Logs resources narrowly,
and uses `Resource: "*"` only for CloudWatch metric reads where AWS IAM requires it.

## Static Examples

Example IAM policies are also provided in:

- [`examples/iam/lambdaopt-readonly-policy.json`](../examples/iam/lambdaopt-readonly-policy.json)
- [`examples/iam/lambdaopt-benchmark-policy.json`](../examples/iam/lambdaopt-benchmark-policy.json)
- [`examples/iam/lambdaopt-analyze-with-logs-policy.json`](../examples/iam/lambdaopt-analyze-with-logs-policy.json)
- [`examples/iam/lambdaopt-watch-dry-run-policy.json`](../examples/iam/lambdaopt-watch-dry-run-policy.json)

Replace these placeholders before use:

- `REGION`
- `ACCOUNT_ID`
- `FUNCTION_NAME`
- `LOG_GROUP_NAME`

For multiple candidate test functions, add each approved function ARN to the `Resource` list for
`lambda:InvokeFunction`.

## Safety Notes

- Do not use `AdministratorAccess` for LambdaOpt.
- Prefer AWS profiles, SSO, or IAM roles.
- Grant `lambda:InvokeFunction` only for approved benchmark/test functions.
- LambdaOpt does not need mutation actions such as `lambda:UpdateFunctionConfiguration`,
  `lambda:PutFunctionConcurrency`, `lambda:PutProvisionedConcurrencyConfig`, or
  `lambda:DeleteProvisionedConcurrencyConfig`.
- Generated policies are local JSON documents; generating a policy does not attach it to any user,
  role, or group.
