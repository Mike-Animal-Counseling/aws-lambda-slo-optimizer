"""Optional Streamlit dashboard for LambdaOpt report directories."""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lambdaopt.exceptions import LambdaOptConfigError

BENCHMARK_RESULTS_FILE = "benchmark_results.json"
RECOMMENDED_CONFIG_FILE = "recommended_config.json"
CLOUDWATCH_ANALYSIS_FILE = "cloudwatch_analysis.json"
COST_VS_P95_CHART_FILE = "cost_vs_p95.png"


@dataclass(frozen=True)
class DashboardData:
    """Loaded report files used by the optional dashboard."""

    report_dir: Path
    benchmark_results: list[dict[str, Any]]
    recommendation: dict[str, Any]
    cloudwatch_analysis: dict[str, Any] | None = None


def load_dashboard_data(report_dir: Path) -> DashboardData:
    """Load dashboard inputs from a LambdaOpt report directory."""
    benchmark_path = report_dir / BENCHMARK_RESULTS_FILE
    recommendation_path = report_dir / RECOMMENDED_CONFIG_FILE

    if not report_dir.exists():
        raise LambdaOptConfigError(f"Report directory does not exist: {report_dir}")
    if not benchmark_path.exists():
        raise LambdaOptConfigError(f"Missing {BENCHMARK_RESULTS_FILE} in {report_dir}")
    if not recommendation_path.exists():
        raise LambdaOptConfigError(f"Missing {RECOMMENDED_CONFIG_FILE} in {report_dir}")

    benchmark_payload = _read_json_file(benchmark_path)
    recommendation = _read_json_file(recommendation_path)
    results = benchmark_payload.get("results") if isinstance(benchmark_payload, dict) else None
    if not isinstance(results, list):
        raise LambdaOptConfigError(f"{BENCHMARK_RESULTS_FILE} must contain a results array.")
    if not isinstance(recommendation, dict):
        raise LambdaOptConfigError(f"{RECOMMENDED_CONFIG_FILE} must contain a JSON object.")

    cloudwatch_path = report_dir / CLOUDWATCH_ANALYSIS_FILE
    cloudwatch_analysis = _read_json_file(cloudwatch_path) if cloudwatch_path.exists() else None
    if cloudwatch_analysis is not None and not isinstance(cloudwatch_analysis, dict):
        raise LambdaOptConfigError(f"{CLOUDWATCH_ANALYSIS_FILE} must contain a JSON object.")

    return DashboardData(
        report_dir=report_dir,
        benchmark_results=[_ensure_dict(item, BENCHMARK_RESULTS_FILE) for item in results],
        recommendation=recommendation,
        cloudwatch_analysis=cloudwatch_analysis,
    )


def launch_dashboard(report_dir: Path) -> None:
    """Launch Streamlit for a report directory."""
    _ensure_streamlit_installed()
    app_path = Path(__file__).resolve()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--",
            "--report",
            str(report_dir),
        ],
        check=False,
    )


def render_dashboard(data: DashboardData) -> None:
    """Render dashboard contents with Streamlit."""
    st = _import_streamlit()
    st.set_page_config(page_title="LambdaOpt Dashboard", layout="wide")
    st.title("LambdaOpt Report Dashboard")
    st.caption(str(data.report_dir))

    _render_recommendation(st, data.recommendation)
    _render_benchmark_table(st, data.benchmark_results)
    _render_cost_vs_p95(st, data)
    _render_pareto_frontier(st, data.benchmark_results)
    _render_cold_start_analysis(st, data)
    _render_cloudwatch_analysis(st, data.cloudwatch_analysis)


def main(argv: list[str] | None = None) -> None:
    """Streamlit script entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    render_dashboard(load_dashboard_data(args.report))


def _render_recommendation(st: Any, recommendation: dict[str, Any]) -> None:
    config = recommendation.get("recommended_config", {})
    st.header("Recommendation")
    col1, col2, col3 = st.columns(3)
    col1.metric("Memory", f"{config.get('memory_mb', 'unknown')} MB")
    col2.metric("Architecture", str(config.get("architecture", "unknown")))
    col3.metric("Confidence", f"{float(recommendation.get('confidence', 0)):.0%}")
    st.write(recommendation.get("reason_summary", "No recommendation summary available."))
    warnings = recommendation.get("warnings", [])
    if warnings:
        st.warning("\n".join(str(warning) for warning in warnings))


def _render_benchmark_table(st: Any, results: list[dict[str, Any]]) -> None:
    st.header("Benchmark Results")
    st.dataframe(_benchmark_rows(results), use_container_width=True)


def _render_cost_vs_p95(st: Any, data: DashboardData) -> None:
    st.header("Cost vs p95")
    chart_path = data.report_dir / COST_VS_P95_CHART_FILE
    if chart_path.exists():
        st.image(str(chart_path), caption="Cost vs p95 latency")
        return
    st.scatter_chart(_benchmark_rows(data.benchmark_results), x="p95_ms", y="total_cost_usd")


def _render_pareto_frontier(st: Any, results: list[dict[str, Any]]) -> None:
    st.header("Pareto Frontier")
    frontier = [row for row in _benchmark_rows(results) if row["pareto_status"] == "frontier"]
    dominated = [row for row in _benchmark_rows(results) if row["pareto_status"] == "dominated"]
    col1, col2 = st.columns(2)
    col1.metric("Frontier configs", len(frontier))
    col2.metric("Dominated configs", len(dominated))
    st.dataframe(frontier, use_container_width=True)


def _render_cold_start_analysis(st: Any, data: DashboardData) -> None:
    st.header("Cold Start Analysis")
    cold_start = None
    if data.cloudwatch_analysis:
        cold_start = data.cloudwatch_analysis.get("cold_start_analysis")
    if isinstance(cold_start, dict):
        col1, col2, col3 = st.columns(3)
        col1.metric("Cold start rate", f"{float(cold_start.get('cold_start_rate', 0)):.1%}")
        col2.metric("Cold starts", int(cold_start.get("cold_start_count", 0)))
        col3.metric("REPORT lines", int(cold_start.get("total_reports", 0)))
        st.write(cold_start.get("diagnosis", "No diagnosis available."))
        return

    rates = [float(item.get("cold_start_rate", 0)) for item in data.benchmark_results]
    if rates:
        st.metric("Max benchmark cold start rate", f"{max(rates):.1%}")
    st.info("No CloudWatch Logs cold-start analysis file was found in this report directory.")


def _render_cloudwatch_analysis(st: Any, cloudwatch_analysis: dict[str, Any] | None) -> None:
    st.header("CloudWatch Analysis")
    if cloudwatch_analysis is None:
        st.info("No CloudWatch analysis file was found in this report directory.")
        return
    col1, col2, col3 = st.columns(3)
    col1.metric("Invocations", int(cloudwatch_analysis.get("total_invocations", 0)))
    col2.metric("p95", _format_ms(cloudwatch_analysis.get("observed_p95_ms")))
    col3.metric("p99", _format_ms(cloudwatch_analysis.get("observed_p99_ms")))
    recommendations = cloudwatch_analysis.get("recommendations", [])
    if recommendations:
        st.subheader("Recommendations")
        for recommendation in recommendations:
            st.write(f"- {recommendation}")
    warnings = cloudwatch_analysis.get("warnings", [])
    if warnings:
        st.warning("\n".join(str(warning) for warning in warnings))


def _benchmark_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in results:
        config = item.get("config", {})
        latency = item.get("latency", {})
        cost = item.get("cost", {})
        rows.append(
            {
                "memory_mb": config.get("memory_mb"),
                "architecture": config.get("architecture"),
                "p50_ms": latency.get("p50_ms"),
                "p95_ms": latency.get("p95_ms"),
                "p99_ms": latency.get("p99_ms"),
                "cold_start_rate": item.get("cold_start_rate"),
                "total_cost_usd": cost.get("total_cost_usd"),
                "slo_passed": item.get("slo_passed"),
                "pareto_status": "dominated" if item.get("dominated") else "frontier",
            }
        )
    return rows


def _format_ms(value: Any) -> str:
    return "unknown" if value is None else f"{float(value):.1f} ms"


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LambdaOptConfigError(f"Invalid JSON file: {path}") from exc
    except OSError as exc:
        raise LambdaOptConfigError(f"Could not read JSON file: {path}") from exc


def _ensure_dict(value: Any, source: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise LambdaOptConfigError(f"{source} contains a non-object result item.")


def _ensure_streamlit_installed() -> None:
    _import_streamlit()


def _import_streamlit() -> Any:
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        raise LambdaOptConfigError(
            "The dashboard requires the optional Streamlit dependency. "
            'Install it with: python -m pip install "aws-lambda-slo-optimizer[dashboard]" '
            'or python -m pip install -e ".[dashboard]"'
        ) from exc
    return st


if __name__ == "__main__":
    main()
