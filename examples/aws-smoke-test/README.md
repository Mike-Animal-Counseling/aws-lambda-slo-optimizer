# LambdaOpt AWS Smoke Test Example

This directory contains a minimal Python Lambda function for validating LambdaOpt in a sandbox or non-production AWS account.

## Files

- `handler.py`: simple Lambda handler.
- `event.json`: payload for `lambdaopt bench`.
- `template.yaml`: optional AWS SAM/CloudFormation template.

## Deploy with AWS SAM

If you use AWS SAM:

```bash
sam build --template-file examples/aws-smoke-test/template.yaml
sam deploy --guided
```

Use a stack name such as:

```text
lambdaopt-smoke-test
```

After deployment, use the function name from the stack output or AWS Console.

## Manual Zip Deployment

You can also create a Lambda function manually with runtime Python 3.11 or newer and handler:

```text
handler.handler
```

Use `event.json` as the payload for LambdaOpt:

```bash
lambdaopt bench my-test-function --trials 20 --payload examples/aws-smoke-test/event.json --region us-east-1 --p95 500 --output reports/smoke
```

This example is intentionally minimal and should not be used as a production application.
