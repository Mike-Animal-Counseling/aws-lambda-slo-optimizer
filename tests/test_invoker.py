from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from lambdaopt.benchmark.invoker import invoke_lambda_safely, load_json_payload
from lambdaopt.exceptions import AwsPermissionError


class FakeInvokeClient:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = responses
        self.calls = 0

    def invoke(
        self,
        *,
        FunctionName: str,
        InvocationType: str,
        Payload: bytes,
    ) -> dict[str, Any]:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_invoke_lambda_safely_collects_latency_and_response_size() -> None:
    client = FakeInvokeClient(
        [
            {
                "StatusCode": 200,
                "Payload": BytesIO(b'{"ok":true}'),
            }
        ]
    )

    sample = invoke_lambda_safely(client=client, function_name="fn", payload=b"{}")

    assert sample.latency_ms >= 0
    assert sample.status_code == 200
    assert sample.function_error is None
    assert sample.payload_response_size_bytes == len(b'{"ok":true}')
    assert sample.succeeded is True


def test_invoke_lambda_safely_captures_function_error() -> None:
    client = FakeInvokeClient(
        [
            {
                "StatusCode": 200,
                "FunctionError": "Unhandled",
                "Payload": BytesIO(b'{"error":"boom"}'),
            }
        ]
    )

    sample = invoke_lambda_safely(client=client, function_name="fn", payload=b"{}")

    assert sample.function_error == "Unhandled"
    assert sample.succeeded is False


def test_invoke_lambda_safely_retries_transient_errors() -> None:
    transient = ClientError(
        {
            "Error": {
                "Code": "TooManyRequestsException",
                "Message": "slow down",
            }
        },
        "Invoke",
    )
    client = FakeInvokeClient(
        [
            transient,
            {
                "StatusCode": 200,
                "Payload": BytesIO(b"{}"),
            },
        ]
    )

    sample = invoke_lambda_safely(
        client=client,
        function_name="fn",
        payload=b"{}",
        retry_backoff_seconds=0,
    )

    assert sample.status_code == 200
    assert sample.attempt_count == 2
    assert client.calls == 2


def test_invoke_lambda_safely_wraps_permission_errors() -> None:
    denied = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "not allowed",
            }
        },
        "Invoke",
    )
    client = FakeInvokeClient([denied])

    with pytest.raises(AwsPermissionError):
        invoke_lambda_safely(client=client, function_name="fn", payload=b"{}")


def test_load_json_payload_reads_bytes_without_exposing_contents(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"secret":"value"}', encoding="utf-8")

    payload = load_json_payload(payload_path)

    assert payload == b'{"secret":"value"}'
