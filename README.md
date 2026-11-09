# LambdaOpt

**Find the lowest-cost AWS Lambda configuration that meets your p95 latency target.**

[![CI](https://github.com/Mike-Animal-Counseling/aws-lambda-slo-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/Mike-Animal-Counseling/aws-lambda-slo-optimizer/actions/workflows/ci.yml) · Beta · Python 3.11+

LambdaOpt compares benchmark candidates by estimated cost and tail latency. Use CloudWatch metrics and cold-start logs to investigate why a deployed function is missing its target.

## Try it locally

Requires Python 3.11+. On Windows, use the [PowerShell setup](docs/installation.md#from-source).

```bash
git clone https://github.com/Mike-Animal-Counseling/aws-lambda-slo-optimizer.git
cd aws-lambda-slo-optimizer
python -m venv .venv
source .venv/bin/activate
python -m pip install .
lambdaopt start
```

The demo uses synthetic data and needs no AWS credentials. Open `reports/start/optimization_report.md` for the recommendation, p95/p99 measurements, and cost estimates.

Two rows from the demo report for a **500 ms p95 target** and 1 million monthly requests.

| Candidate | p95 | p99 | Est. monthly cost | Result |
| --- | ---: | ---: | ---: | --- |
| 512 MB arm64 | 633.1 ms | 692.9 ms | `$3.91` | Misses target |
| 1024 MB arm64 | 357.9 ms | 479.4 ms | `$4.38` | Recommended |

## Use it with AWS

Start with the [sandbox walkthrough](docs/smoke-test.md). CloudWatch analysis reads metrics and optional logs. Benchmarking can invoke explicitly selected functions, so use test targets. LambdaOpt leaves Lambda configuration unchanged.

## Documentation

- [CLI workflows](docs/usage.md) and [IAM permissions](docs/iam-permissions.md)
- [Architecture](docs/architecture.md) and [recommendation logic](docs/design.md)
- [Safety](docs/safety.md) and [contributing](CONTRIBUTING.md)

[MIT license](LICENSE)
