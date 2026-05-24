# Security

LambdaOpt is designed to use standard AWS identity mechanisms and least-privilege permissions. It does not ask for AWS access keys and does not require credentials for local-only workflows such as `simulate` or `tune --input`.

## Credential Handling

LambdaOpt uses boto3's default credential provider chain. Recommended credential sources include:

- AWS named profiles,
- AWS SSO-backed profiles,
- IAM roles for EC2, ECS, or other runtime environments,
- short-lived environment credentials managed outside LambdaOpt.

Examples:

```bash
lambdaopt plan my-function --p95 500 --region us-east-1 --profile default
lambdaopt analyze my-function --window 24h --p95 500 --region us-east-1 --profile prod-readonly
```

LambdaOpt never prompts for or stores AWS access keys.

LambdaOpt does not print raw `os.environ`, does not serialize boto3 credential objects, and does not ask for CLI options such as `--access-key`, `--secret-key`, or `--session-token`.

## Least Privilege

Do not run LambdaOpt with `AdministratorAccess`. Use the narrowest policy that matches the command you need.

Generate a least-privilege policy for a specific workflow:

```bash
lambdaopt iam generate --mode analyze-with-logs --function my-function --region us-east-1 --account-id ACCOUNT_ID
```

Recommended starting points:

- Read metadata and CloudWatch metrics: [`examples/iam/lambdaopt-readonly-policy.json`](../examples/iam/lambdaopt-readonly-policy.json)
- Benchmark by invoking approved functions: [`examples/iam/lambdaopt-benchmark-policy.json`](../examples/iam/lambdaopt-benchmark-policy.json)
- Analyze metrics and cold-start logs: [`examples/iam/lambdaopt-analyze-with-logs-policy.json`](../examples/iam/lambdaopt-analyze-with-logs-policy.json)

See [IAM Permissions](iam-permissions.md) for a command-by-command matrix.

## First Real AWS Run

Use a sandbox account or non-production Lambda function for your first real AWS check.

Step 1: verify local and AWS readiness.

```bash
lambdaopt doctor my-function --region us-east-1
```

Step 2: generate a least-privilege policy for the workflow.

```bash
lambdaopt iam generate --mode analyze-with-logs --function my-function --region us-east-1 --account-id ACCOUNT_ID
```

Step 3: read Lambda metadata and review the benchmark plan.

```bash
lambdaopt plan my-function --p95 500 --region us-east-1
```

Step 4: analyze CloudWatch metrics without mutation.

```bash
lambdaopt analyze my-function --window 24h --p95 500
```

## Production Mutation

Current LambdaOpt commands do not mutate production infrastructure. They do not update Lambda memory, architecture, timeout, aliases, versions, or provisioned concurrency.

Future unsafe mutation modes, if added, should be explicit, opt-in, heavily confirmed, and documented separately. They are not part of the current default workflow.

## Payload Safety

Benchmark commands invoke Lambda with a payload file. Do not pass secrets in payloads unless the function genuinely requires them for the benchmark.

LambdaOpt avoids logging raw payload contents. Payload and report helpers redact likely sensitive keys such as:

- `password`
- `token`
- `secret`
- `authorization`
- `api_key`

Redaction is a defensive helper, not a substitute for avoiding unnecessary secrets.

Reports include safe payload metadata such as file path, byte size, and SHA256 hash. They do not include raw payload contents by default.

## Logs and Reports

CloudWatch Logs analysis reads Lambda REPORT lines for cold-start signals. LambdaOpt looks for aggregate fields such as duration, billed duration, memory size, and init duration. It should not require application log messages containing business data.

Generated reports are local files. Treat report directories according to your organization's data handling policy, especially if metadata or function names are sensitive.

## CI

The project CI does not require AWS credentials. Tests use local fixtures and mocks rather than real AWS calls.

LambdaOpt does not phone home, send analytics, or include telemetry exporters.
