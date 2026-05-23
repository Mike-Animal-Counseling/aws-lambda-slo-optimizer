"""Read-only CloudWatch metrics client for Lambda production analysis."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from lambdaopt.aws.lambda_client import _client_error_to_lambdaopt_error
from lambdaopt.aws.session import create_cloudwatch_boto_client
from lambdaopt.exceptions import AwsCredentialsError, AwsIntegrationError, LambdaOptValidationError

SUPPORTED_WINDOWS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
LAMBDA_NAMESPACE = "AWS/Lambda"
FUNCTION_NAME_DIMENSION = "FunctionName"


class CloudWatchBotoClient(Protocol):
    """Subset of CloudWatch client methods used by LambdaOpt."""

    def get_metric_data(
        self,
        *,
        MetricDataQueries: list[dict[str, Any]],
        StartTime: datetime,
        EndTime: datetime,
        ScanBy: str,
    ) -> dict[str, Any]:
        """Return CloudWatch metric data."""


@dataclass(frozen=True)
class MetricPoint:
    """One CloudWatch metric datapoint."""

    timestamp: datetime
    value: float


@dataclass(frozen=True)
class MetricSeries:
    """Named time series returned from CloudWatch."""

    label: str
    points: list[MetricPoint]


@dataclass(frozen=True)
class LambdaCloudWatchMetrics:
    """CloudWatch metric series for one Lambda function and time window."""

    function_name: str
    start_time: datetime
    end_time: datetime
    period_seconds: int
    series: dict[str, MetricSeries]


class CloudWatchClient:
    """Read-only wrapper around CloudWatch Lambda metrics APIs."""

    def __init__(self, boto_client: CloudWatchBotoClient) -> None:
        self._client = boto_client

    @classmethod
    def from_session_options(
        cls,
        *,
        profile: str | None = None,
        region: str | None = None,
    ) -> "CloudWatchClient":
        """Create a CloudWatchClient from optional AWS profile and region."""
        return cls(create_cloudwatch_boto_client(profile=profile, region=region))

    def fetch_lambda_metrics(
        self,
        *,
        function_name: str,
        start_time: datetime,
        end_time: datetime,
        period_seconds: int,
    ) -> LambdaCloudWatchMetrics:
        """Fetch Lambda metrics relevant to SLO and production health analysis."""
        queries = _build_metric_queries(function_name=function_name, period_seconds=period_seconds)
        try:
            response = self._client.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampAscending",
            )
        except NoCredentialsError as exc:
            raise AwsCredentialsError(
                "AWS credentials were not found. Configure credentials or pass --profile."
            ) from exc
        except ClientError as exc:
            raise _client_error_to_lambdaopt_error(exc) from exc
        except BotoCoreError as exc:
            raise AwsIntegrationError(f"Could not read CloudWatch metrics: {exc}") from exc

        return LambdaCloudWatchMetrics(
            function_name=function_name,
            start_time=start_time,
            end_time=end_time,
            period_seconds=period_seconds,
            series=_parse_metric_data_results(response.get("MetricDataResults", [])),
        )


def parse_window(window: str, *, now: datetime | None = None) -> tuple[datetime, datetime, int]:
    """Parse supported observation window strings into start, end, and period."""
    if window not in SUPPORTED_WINDOWS:
        supported = ", ".join(sorted(SUPPORTED_WINDOWS))
        raise LambdaOptValidationError(f"Unsupported window '{window}'. Use one of: {supported}.")

    end_time = now or datetime.now(UTC)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=UTC)
    duration = SUPPORTED_WINDOWS[window]
    return end_time - duration, end_time, select_period_seconds(window)


def select_period_seconds(window: str) -> int:
    """Select a practical CloudWatch period for a supported analysis window."""
    if window in {"15m", "1h"}:
        return 60
    if window in {"6h", "24h"}:
        return 300
    if window == "7d":
        return 3600
    raise LambdaOptValidationError(f"Unsupported window '{window}'.")


def _build_metric_queries(function_name: str, period_seconds: int) -> list[dict[str, Any]]:
    metrics = [
        ("invocations", "Invocations", "Sum"),
        ("duration_average", "Duration", "Average"),
        ("duration_maximum", "Duration", "Maximum"),
        ("duration_p50", "Duration", "p50"),
        ("duration_p95", "Duration", "p95"),
        ("duration_p99", "Duration", "p99"),
        ("errors", "Errors", "Sum"),
        ("throttles", "Throttles", "Sum"),
        ("concurrent_executions", "ConcurrentExecutions", "Maximum"),
    ]
    return [
        {
            "Id": metric_id,
            "MetricStat": {
                "Metric": {
                    "Namespace": LAMBDA_NAMESPACE,
                    "MetricName": metric_name,
                    "Dimensions": [
                        {"Name": FUNCTION_NAME_DIMENSION, "Value": function_name},
                    ],
                },
                "Period": period_seconds,
                "Stat": stat,
            },
            "ReturnData": True,
        }
        for metric_id, metric_name, stat in metrics
    ]


def _parse_metric_data_results(results: list[dict[str, Any]]) -> dict[str, MetricSeries]:
    parsed: dict[str, MetricSeries] = {}
    for result in results:
        metric_id = str(result.get("Id", ""))
        timestamps = result.get("Timestamps", [])
        values = result.get("Values", [])
        parsed[metric_id] = MetricSeries(
            label=str(result.get("Label", metric_id)),
            points=[
                MetricPoint(timestamp=timestamp, value=float(value))
                for timestamp, value in zip(timestamps, values, strict=False)
            ],
        )
    return parsed
