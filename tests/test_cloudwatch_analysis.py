from datetime import UTC, datetime, timedelta
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

import lambdaopt.cli as cli
from lambdaopt.analysis.cloudwatch_analysis import analyze_cloudwatch_metrics
from lambdaopt.aws.cloudwatch_client import LambdaCloudWatchMetrics, MetricPoint, MetricSeries
from lambdaopt.aws.lambda_client import LambdaFunctionConfiguration
from lambdaopt.aws.logs_client import LogMessage
from lambdaopt.models import LambdaConfig


def test_cloudwatch_analysis_marks_healthy_p95() -> None:
    analysis = analyze_cloudwatch_metrics(
        metrics=_metrics(duration_p95=300, duration_p99=360),
        current_config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        target_p95_ms=500,
        monthly_requests=1_000_000,
        window_label="24h",
    )

    assert analysis.slo_passed is True
    assert analysis.risk_signals == []
    assert "No immediate change recommended" in analysis.recommendations[0]


def test_cloudwatch_analysis_marks_risky_p95_and_tail_latency() -> None:
    analysis = analyze_cloudwatch_metrics(
        metrics=_metrics(duration_p95=510, duration_p99=1200),
        current_config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        target_p95_ms=500,
        monthly_requests=1_000_000,
        window_label="24h",
    )

    assert analysis.slo_passed is False
    assert any("p95 is at or above" in signal for signal in analysis.risk_signals)
    assert any("p99 is much higher" in signal for signal in analysis.risk_signals)
    assert any("cold starts" in recommendation for recommendation in analysis.recommendations)


def test_cloudwatch_analysis_includes_pc_recommendation_when_cold_data_exists() -> None:
    from lambdaopt.analysis.cold_start import analyze_cold_starts_from_messages

    cold_start_analysis = analyze_cold_starts_from_messages(
        [
            (
                "REPORT RequestId: abc\tDuration: 100.00 ms\tBilled Duration: 101 ms\t"
                "Memory Size: 1024 MB\tMax Memory Used: 128 MB\tInit Duration: 250.00 ms"
            )
            for _ in range(10)
        ],
        observed_p95_ms=300,
        observed_p99_ms=900,
    )

    analysis = analyze_cloudwatch_metrics(
        metrics=_metrics(duration_p95=300, duration_p99=900),
        current_config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        target_p95_ms=500,
        monthly_requests=1_000_000,
        window_label="24h",
        cold_start_analysis=cold_start_analysis,
    )

    assert analysis.provisioned_concurrency_recommendation is not None
    assert analysis.provisioned_concurrency_recommendation.expected_benefit == "high"


def test_cloudwatch_analysis_flags_throttles() -> None:
    analysis = analyze_cloudwatch_metrics(
        metrics=_metrics(duration_p95=200, throttles=3),
        current_config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        target_p95_ms=500,
        monthly_requests=1_000_000,
        window_label="24h",
    )

    assert analysis.throttles == 3
    assert any("Throttles are present" in signal for signal in analysis.risk_signals)
    assert any("Investigate throttles" in item for item in analysis.recommendations)


def test_cloudwatch_analysis_missing_percentiles_degrades_gracefully() -> None:
    metrics = _metrics(duration_p95=None, duration_p99=None)

    analysis = analyze_cloudwatch_metrics(
        metrics=metrics,
        current_config=LambdaConfig(memory_mb=1024, architecture="arm64"),
        target_p95_ms=500,
        monthly_requests=1_000_000,
        window_label="24h",
    )

    assert analysis.slo_passed is None
    assert any("p95 Duration data was unavailable" in warning for warning in analysis.warnings)
    assert any("Run benchmark" in item for item in analysis.recommendations)


def test_analyze_cli_with_mocked_clients_creates_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeLambdaClient:
        def get_function_configuration(self, function_name: str) -> LambdaFunctionConfiguration:
            return LambdaFunctionConfiguration(
                config=LambdaConfig(memory_mb=1024, architecture="arm64", timeout_seconds=30),
                metadata={"runtime": "python3.12", "function_name": function_name},
            )

    class FakeCloudWatchClient:
        def fetch_lambda_metrics(
            self,
            *,
            function_name: str,
            start_time: datetime,
            end_time: datetime,
            period_seconds: int,
        ) -> LambdaCloudWatchMetrics:
            return _metrics(duration_p95=210, duration_p99=260, function_name=function_name)

    class FakeLogsClient:
        def fetch_lambda_report_logs(
            self,
            *,
            function_name: str,
            start_time: datetime,
            end_time: datetime,
        ) -> list[LogMessage]:
            return [
                LogMessage(
                    timestamp=start_time,
                    message=(
                        "REPORT RequestId: abc\tDuration: 100.00 ms\t"
                        "Billed Duration: 101 ms\tMemory Size: 1024 MB\t"
                        "Max Memory Used: 128 MB\tInit Duration: 250.00 ms"
                    ),
                )
            ]

    def fake_lambda_factory(
        *,
        profile: str | None = None,
        region: str | None = None,
    ) -> FakeLambdaClient:
        assert profile is None
        assert region == "us-east-1"
        return FakeLambdaClient()

    def fake_cloudwatch_factory(
        *,
        profile: str | None = None,
        region: str | None = None,
    ) -> FakeCloudWatchClient:
        assert profile is None
        assert region == "us-east-1"
        return FakeCloudWatchClient()

    def fake_logs_factory(
        *,
        profile: str | None = None,
        region: str | None = None,
    ) -> FakeLogsClient:
        assert profile is None
        assert region == "us-east-1"
        return FakeLogsClient()

    monkeypatch.setattr(cli, "lambda_client_factory", fake_lambda_factory)
    monkeypatch.setattr(cli, "cloudwatch_client_factory", fake_cloudwatch_factory)
    monkeypatch.setattr(cli, "logs_client_factory", fake_logs_factory)
    runner = CliRunner()
    output_dir = tmp_path / "analyze"

    result = runner.invoke(
        cli.app,
        [
            "analyze",
            "my-function",
            "--window",
            "24h",
            "--p95",
            "500",
            "--region",
            "us-east-1",
            "--monthly-requests",
            "1000000",
            "--include-logs",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    report = (output_dir / "optimization_report.md").read_text(encoding="utf-8")
    assert (output_dir / "cloudwatch_analysis.json").exists()
    assert "LambdaOpt CloudWatch Analysis Report" in report
    assert "Observed p95: 210.0 ms" in report
    assert "Cold starts: 1" in report
    assert "SLO health: healthy" in result.stdout


def _metrics(
    *,
    duration_p95: float | None,
    duration_p99: float | None = 280,
    throttles: float = 0,
    function_name: str = "my-function",
) -> LambdaCloudWatchMetrics:
    start = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=24)
    series = {
        "invocations": _series("Invocations", [100, 200]),
        "duration_average": _series("Duration Average", [100, 120]),
        "duration_p50": _series("Duration p50", [90, 100]),
        "errors": _series("Errors", [0, 0]),
        "throttles": _series("Throttles", [0, throttles]),
        "concurrent_executions": _series("ConcurrentExecutions", [3, 5]),
    }
    if duration_p95 is not None:
        series["duration_p95"] = _series("Duration p95", [duration_p95])
    if duration_p99 is not None:
        series["duration_p99"] = _series("Duration p99", [duration_p99])
    return LambdaCloudWatchMetrics(
        function_name=function_name,
        start_time=start,
        end_time=end,
        period_seconds=300,
        series=series,
    )


def _series(label: str, values: list[float]) -> MetricSeries:
    start = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    return MetricSeries(
        label=label,
        points=[
            MetricPoint(timestamp=start + timedelta(minutes=index), value=value)
            for index, value in enumerate(values)
        ],
    )
