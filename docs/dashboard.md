# Dashboard

LambdaOpt includes an optional local Streamlit dashboard for viewing generated report directories.

The dashboard is not required for CLI usage. Core commands such as `simulate`, `tune`, `plan`, `bench`, `analyze`, and `watch` do not require Streamlit.

## Installation

Install the dashboard extra:

```bash
python -m pip install -e ".[dashboard]"
```

For development with every optional feature:

```bash
python -m pip install -e ".[dev,aws,charts,dashboard]"
```

## Usage

Generate a report:

```bash
lambdaopt tune --input examples/sample_results.json --p95 500 --monthly-requests 1000000 --output reports/sample
```

Open the dashboard:

```bash
lambdaopt dashboard --report reports/sample
```

## What It Shows

The dashboard loads:

- `benchmark_results.json`
- `recommended_config.json`
- `cloudwatch_analysis.json` when present
- `cost_vs_p95.png` when present

It displays:

- recommendation summary,
- benchmark table,
- cost vs p95 chart,
- Pareto frontier table,
- cold-start summary when data is available,
- CloudWatch analysis when data is available.

## Limitations

The dashboard is a local viewer for report artifacts. It does not call AWS, run benchmarks, or mutate infrastructure. If `streamlit` is not installed, `lambdaopt dashboard` prints an install hint instead of affecting the rest of the CLI.
