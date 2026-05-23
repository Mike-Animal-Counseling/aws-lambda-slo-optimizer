"""Safe synchronous Lambda invocation helpers for benchmarking."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError, ConnectTimeoutError, ReadTimeoutError

from lambdaopt.exceptions import (
    AwsCredentialsError,
    AwsIntegrationError,
    AwsPermissionError,
    AwsTimeoutError,
    LambdaOptValidationError,
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
TRANSIENT_ERROR_CODES = {
    "EC2ThrottledException",
    "ServiceException",
    "ThrottlingException",
    "TooManyRequestsException",
}
PERMISSION_ERROR_CODES = {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}
CREDENTIAL_ERROR_CODES = {
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "UnrecognizedClientException",
}


class LambdaInvokeClient(Protocol):
    """Subset of boto3 Lambda client methods used for invocation benchmarking."""

    def invoke(
        self,
        *,
        FunctionName: str,
        InvocationType: str,
        Payload: bytes,
    ) -> dict[str, Any]:
        """Synchronously invoke a Lambda function."""


@dataclass(frozen=True)
class InvocationSample:
    """One client-observed Lambda invocation benchmark sample."""

    latency_ms: float
    status_code: int
    function_error: str | None
    payload_response_size_bytes: int
    attempt_count: int

    @property
    def succeeded(self) -> bool:
        """Return whether the Lambda invocation completed without a function/platform error."""
        return self.status_code < 400 and self.function_error is None


def load_json_payload(path: Path) -> bytes:
    """Load a JSON payload file without returning or logging sensitive content."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LambdaOptValidationError(f"Payload file does not exist: {path}") from exc
    except OSError as exc:
        raise LambdaOptValidationError(f"Could not read payload file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LambdaOptValidationError(f"Payload file is not valid JSON: {path}") from exc

    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def invoke_lambda_safely(
    *,
    client: LambdaInvokeClient,
    function_name: str,
    payload: bytes,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> InvocationSample:
    """Invoke Lambda synchronously with bounded retries and client-side timing."""
    if max_attempts < 1:
        raise LambdaOptValidationError("max_attempts must be at least 1.")

    for attempt in range(1, max_attempts + 1):
        started_at = time.perf_counter()
        try:
            response = client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=payload,
            )
            latency_ms = (time.perf_counter() - started_at) * 1000
            return _sample_from_response(response, latency_ms=latency_ms, attempt_count=attempt)
        except (ConnectTimeoutError, ReadTimeoutError) as exc:
            if attempt == max_attempts:
                raise AwsTimeoutError(
                    f"Lambda invocation timed out after {max_attempts} attempts."
                ) from exc
            _sleep_before_retry(retry_backoff_seconds, attempt)
        except ClientError as exc:
            if _is_transient_client_error(exc) and attempt < max_attempts:
                _sleep_before_retry(retry_backoff_seconds, attempt)
                continue
            raise _client_error_to_benchmark_error(exc) from exc
        except BotoCoreError as exc:
            raise AwsIntegrationError(f"Lambda invocation failed: {exc}") from exc

    raise AwsTimeoutError(f"Lambda invocation failed after {max_attempts} attempts.")


def _sample_from_response(
    response: dict[str, Any],
    *,
    latency_ms: float,
    attempt_count: int,
) -> InvocationSample:
    payload_stream = response.get("Payload")
    response_bytes = _read_payload_bytes(payload_stream)
    return InvocationSample(
        latency_ms=latency_ms,
        status_code=int(response.get("StatusCode", 0)),
        function_error=_optional_string(response.get("FunctionError")),
        payload_response_size_bytes=len(response_bytes),
        attempt_count=attempt_count,
    )


def _read_payload_bytes(payload_stream: Any) -> bytes:
    if payload_stream is None:
        return b""
    value = payload_stream.read() if hasattr(payload_stream, "read") else payload_stream
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _is_transient_client_error(exc: ClientError) -> bool:
    return str(exc.response.get("Error", {}).get("Code", "")) in TRANSIENT_ERROR_CODES


def _client_error_to_benchmark_error(exc: ClientError) -> AwsIntegrationError:
    error = exc.response.get("Error", {})
    code = str(error.get("Code", "Unknown"))
    message = str(error.get("Message", str(exc)))

    if code in PERMISSION_ERROR_CODES:
        return AwsPermissionError(f"AWS denied Lambda invocation permission: {message}")
    if code in CREDENTIAL_ERROR_CODES:
        return AwsCredentialsError(f"AWS credentials are invalid or expired: {message}")
    if code in TRANSIENT_ERROR_CODES:
        return AwsTimeoutError(f"Transient Lambda invocation error did not recover: {message}")
    return AwsIntegrationError(f"Lambda invocation failed ({code}): {message}")


def _sleep_before_retry(retry_backoff_seconds: float, attempt: int) -> None:
    if retry_backoff_seconds > 0:
        time.sleep(retry_backoff_seconds * attempt)
