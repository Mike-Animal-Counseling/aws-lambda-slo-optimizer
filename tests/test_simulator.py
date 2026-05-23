from pathlib import Path

from typer.testing import CliRunner

from lambdaopt.analysis.latency import calculate_latency_stats
from lambdaopt.cli import app
from lambdaopt.models import BenchmarkResult
from lambdaopt.simulator.generator import generate_benchmark_results
from lambdaopt.simulator.replay import COLD_START_RISK_WARNING, replay_workload


def test_simulator_returns_non_empty_benchmark_results() -> None:
    results = generate_benchmark_results(workload="cpu-bound", samples=20, seed=123)

    assert results
    assert len(results) == 8
    assert all(result.raw_latencies_ms for result in results)


def test_cpu_bound_latency_generally_decreases_with_memory() -> None:
    results = generate_benchmark_results(workload="cpu-bound", samples=100, seed=123)

    assert _average_p95_for_memory(results, 2048) < _average_p95_for_memory(results, 512)


def test_io_bound_latency_changes_less_than_cpu_bound() -> None:
    cpu_results = generate_benchmark_results(workload="cpu-bound", samples=100, seed=123)
    io_results = generate_benchmark_results(workload="io-bound", samples=100, seed=123)

    cpu_improvement = _average_p95_for_memory(cpu_results, 512) - _average_p95_for_memory(
        cpu_results,
        2048,
    )
    io_improvement = _average_p95_for_memory(io_results, 512) - _average_p95_for_memory(
        io_results,
        2048,
    )

    assert io_improvement < cpu_improvement


def test_cold_start_heavy_has_cold_start_rate_and_warning() -> None:
    results, warnings = replay_workload(workload="cold-start-heavy", samples=100, seed=123)
    cold_start_rates = [
        result.cold_starts / len(result.raw_latencies_ms)
        for result in results
    ]

    assert max(cold_start_rates) > 0
    assert COLD_START_RISK_WARNING in warnings


def test_simulate_command_creates_report(tmp_path: Path) -> None:
    runner = CliRunner()
    output_dir = tmp_path / "cpu"

    result = runner.invoke(
        app,
        [
            "simulate",
            "--workload",
            "cpu-bound",
            "--p95",
            "500",
            "--monthly-requests",
            "1000000",
            "--samples",
            "30",
            "--seed",
            "123",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "benchmark_results.json").exists()
    assert (output_dir / "recommended_config.json").exists()
    assert (output_dir / "optimization_report.md").exists()


def _average_p95_for_memory(results: list[BenchmarkResult], memory_mb: int) -> float:
    matching_results = [
        result for result in results if result.config.memory_mb == memory_mb
    ]
    p95_values = [
        calculate_latency_stats(result.raw_latencies_ms, target_ms=500).p95_ms
        for result in matching_results
    ]
    return sum(p95_values) / len(p95_values)
