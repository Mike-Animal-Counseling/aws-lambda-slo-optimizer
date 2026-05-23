from datetime import UTC, datetime
from typing import Any

from lambdaopt.aws.logs_client import LogsClient, default_lambda_log_group


class FakeLogsBotoClient:
    def __init__(self) -> None:
        self.last_request: dict[str, Any] = {}

    def filter_log_events(
        self,
        *,
        logGroupName: str,
        startTime: int,
        endTime: int,
        filterPattern: str,
        limit: int,
    ) -> dict[str, Any]:
        self.last_request = {
            "logGroupName": logGroupName,
            "startTime": startTime,
            "endTime": endTime,
            "filterPattern": filterPattern,
            "limit": limit,
        }
        return {
            "events": [
                {
                    "timestamp": startTime,
                    "message": (
                        "REPORT RequestId: abc\tDuration: 100.00 ms\t"
                        "Billed Duration: 101 ms\tMemory Size: 1024 MB\t"
                        "Max Memory Used: 128 MB\tInit Duration: 250.00 ms"
                    ),
                },
                {"timestamp": endTime, "message": "not a report"},
            ]
        }


def test_default_lambda_log_group() -> None:
    assert default_lambda_log_group("my-function") == "/aws/lambda/my-function"


def test_logs_client_fetches_report_lines() -> None:
    fake = FakeLogsBotoClient()
    client = LogsClient(fake)
    start = datetime(2026, 5, 23, 11, 0, tzinfo=UTC)
    end = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)

    logs = client.fetch_lambda_report_logs(
        function_name="my-function",
        start_time=start,
        end_time=end,
        limit=25,
    )

    assert fake.last_request["logGroupName"] == "/aws/lambda/my-function"
    assert fake.last_request["filterPattern"] == '"REPORT"'
    assert fake.last_request["limit"] == 25
    assert len(logs) == 1
    assert "Init Duration" in logs[0].message
