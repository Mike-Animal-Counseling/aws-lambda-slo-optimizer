from datetime import UTC, datetime
from typing import Any

import pytest

from lambdaopt.aws.cloudwatch_client import CloudWatchClient, parse_window, select_period_seconds
from lambdaopt.exceptions import LambdaOptValidationError


class FakeCloudWatchBotoClient:
    def __init__(self) -> None:
        self.last_queries: list[dict[str, Any]] = []

    def get_metric_data(
        self,
        *,
        MetricDataQueries: list[dict[str, Any]],
        StartTime: datetime,
        EndTime: datetime,
        ScanBy: str,
    ) -> dict[str, Any]:
        self.last_queries = MetricDataQueries
        return {
            "MetricDataResults": [
                {
                    "Id": "invocations",
                    "Label": "Invocations",
                    "Timestamps": [StartTime, EndTime],
                    "Values": [10, 20],
                },
                {
                    "Id": "duration_p95",
                    "Label": "Duration p95",
                    "Timestamps": [EndTime],
                    "Values": [250],
                },
            ]
        }


def test_parse_window_selects_times_and_periods() -> None:
    now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)

    start, end, period = parse_window("24h", now=now)

    assert end == now
    assert start == datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    assert period == 300
    assert select_period_seconds("1h") == 60
    assert select_period_seconds("7d") == 3600


def test_parse_window_rejects_unsupported_window() -> None:
    with pytest.raises(LambdaOptValidationError):
        parse_window("2h")


def test_cloudwatch_client_fetches_lambda_metric_queries() -> None:
    fake = FakeCloudWatchBotoClient()
    client = CloudWatchClient(fake)
    start = datetime(2026, 5, 23, 11, 0, tzinfo=UTC)
    end = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)

    metrics = client.fetch_lambda_metrics(
        function_name="my-function",
        start_time=start,
        end_time=end,
        period_seconds=60,
    )

    assert metrics.function_name == "my-function"
    assert metrics.series["invocations"].points[0].value == 10
    assert metrics.series["duration_p95"].points[0].value == 250
    metric_names = {
        query["MetricStat"]["Metric"]["MetricName"]
        for query in fake.last_queries
    }
    assert {
        "Invocations",
        "Duration",
        "Errors",
        "Throttles",
        "ConcurrentExecutions",
    } <= metric_names
    assert fake.last_queries[0]["MetricStat"]["Metric"]["Dimensions"] == [
        {"Name": "FunctionName", "Value": "my-function"}
    ]
