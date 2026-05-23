# Installation

LambdaOpt requires Python 3.11 or newer.

## From Source

Clone the repository and install it in editable mode:

```bash
git clone https://github.com/Mike-Animal-Counseling/aws-lambda-slo-optimizer.git
cd aws-lambda-slo-optimizer
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows PowerShell:

```powershell
git clone https://github.com/Mike-Animal-Counseling/aws-lambda-slo-optimizer.git
cd aws-lambda-slo-optimizer
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev,aws,charts]"
```

## Optional Extras

```bash
python -m pip install -e ".[aws]"
python -m pip install -e ".[charts]"
python -m pip install -e ".[dev]"
```

The base install currently includes the AWS SDK because the CLI exposes AWS-aware commands. The `aws` extra is provided so downstream packaging can depend on that capability explicitly.

## AWS Credentials

LambdaOpt uses boto3 credential resolution. You can use environment variables, shared AWS config files, SSO-backed profiles, or instance credentials.

Useful setup commands:

```bash
aws configure
aws sts get-caller-identity
```

You can pass region and profile explicitly:

```bash
lambdaopt plan my-function --p95 500 --region us-east-1 --profile default
```

Or place defaults in `lambdaopt.yaml`:

```yaml
default_region: us-east-1
default_profile: default
default_monthly_requests: 1000000
safety:
  allow_production_mutation: false
  require_confirmation: true
```

## Safety

LambdaOpt does not mutate production Lambda configuration by default. Current AWS workflows are read-only or invoke explicitly named functions for benchmarking. Candidate benchmarking uses separate test functions from a mapping file instead of changing `$LATEST` or production aliases.
