# LambdaOpt

SLO-aware AWS Lambda deployment optimizer for finding the cheapest safe configuration that satisfies p95/p99 latency goals.

## Current Status

This repository is in foundation mode. The Python package, CLI shell, configuration models, linting, formatting, typing, and test scaffolding are in place. AWS integrations, benchmarking, analysis, recommendation, and reporting logic are planned but not implemented yet.

## Planned Commands

- `lambdaopt tune` - benchmark candidate Lambda configurations and recommend a safe deployment target.
- `lambdaopt analyze` - inspect existing CloudWatch metrics and logs for latency, cold starts, and cost signals.
- `lambdaopt watch` - continuously monitor Lambda performance against an SLO.

## Available Commands

```bash
lambdaopt version
```

## Local Development

```bash
make install
make check
```

