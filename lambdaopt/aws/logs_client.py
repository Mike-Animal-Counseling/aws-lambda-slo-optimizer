"""Read-only CloudWatch Logs client for Lambda REPORT lines.

This module uses ``filter_log_events`` instead of Logs Insights because Lambda
REPORT lines are direct log events and this avoids managing asynchronous query
state while still supporting bounded time windows and limits.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from lambdaopt.aws.lambda_client import _client_error_to_lambdaopt_error
from lambdaopt.aws.session import create_logs_boto_client
from lambdaopt.exceptions import AwsCredentialsError, AwsIntegrationError

REPORT_FILTER_PATTERN = '"REPORT"'
DEFAULT_LOG_LIMIT = 1000


class LogsBotoClient(Protocol):
    """Subset of CloudWatch Logs client methods used by LambdaOpt."""

    def filter_log_events(
        self,
        *,
        logGroupName: str,
        startTime: int,
        endTime: int,
        filterPattern: str,
        limit: int,
    ) -> dict[str, Any]:
        """Return matching CloudWatch log events."""


@dataclass(frozen=True)
class LogMessage:
    """CloudWatch Logs event message and timestamp."""

    timestamp: datetime
    message: str


class LogsClient:
    """Read-only wrapper around CloudWatch Logs REPORT line retrieval."""

    def __init__(self, boto_client: LogsBotoClient) -> None:
        self._client = boto_client

    @classmethod
    def from_session_options(
        cls,
        *,
        profile: str | None = None,
        region: str | None = None,
    ) -> "LogsClient":
        """Create a LogsClient from optional AWS profile and region."""
        return cls(create_logs_boto_client(profile=profile, region=region))

    def fetch_lambda_report_logs(
        self,
        *,
        function_name: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = DEFAULT_LOG_LIMIT,
        log_group_name: str | None = None,
    ) -> list[LogMessage]:
        """Fetch Lambda REPORT log lines for a function and time window."""
        group_name = log_group_name or default_lambda_log_group(function_name)
        try:
            response = self._client.filter_log_events(
                logGroupName=group_name,
                startTime=_to_epoch_millis(start_time),
                endTime=_to_epoch_millis(end_time),
                filterPattern=REPORT_FILTER_PATTERN,
                limit=limit,
            )
        except NoCredentialsError as exc:
            raise AwsCredentialsError(
                "AWS credentials were not found. Configure credentials or pass --profile."
            ) from exc
        except ClientError as exc:
            raise _client_error_to_lambdaopt_error(exc) from exc
        except BotoCoreError as exc:
            raise AwsIntegrationError(f"Could not read CloudWatch Logs: {exc}") from exc

        return [
            LogMessage(
                timestamp=datetime.fromtimestamp(event["timestamp"] / 1000, tz=start_time.tzinfo),
                message=str(event.get("message", "")),
            )
            for event in response.get("events", [])
            if "REPORT" in str(event.get("message", ""))
        ]


def default_lambda_log_group(function_name: str) -> str:
    """Return the default CloudWatch log group for a Lambda function."""
    return f"/aws/lambda/{function_name}"


def _to_epoch_millis(value: datetime) -> int:
    return round(value.timestamp() * 1000)
