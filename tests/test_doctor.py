import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import lambdaopt.cli as cli
from lambdaopt.aws.cloudwatch_client import LambdaCloudWatchMetrics, MetricPoint, MetricSeries
from lambdaopt.aws.lambda_client import LambdaFunctionConfiguration
from lambdaopt.doctor import DoctorDependencies, render_doctor_text, run_doctor
from lambdaopt.exceptions import AwsCredentialsError, AwsIntegrationError, AwsPermissionError
from lambdaopt.models import LambdaConfig


class FakeSession:
    region_name = "us-east-1"

    def client(self, service_name: str) -> "FakeStsClient":
        assert service_name == "sts"
        return FakeStsClient()


class FakeStsClient:
    def get_caller_identity(self) -> dict[str, Any]:
        return {
            "Account": "123456789012",
            "Arn": "arn:aws:sts::123456789012:assumed-role/lambdaopt-test/session",
        }


class FakeLambdaClient:
    def __init__(self, *, missing: bool = False) -> None:
        self.missing = missing
        self.invoke_called = False
        self.mutation_called = False

    def get_function_configuration(self, function_name: str) -> LambdaFunctionConfiguration:
        if self.missing:
            raise AwsIntegrationError("ResourceNotFoundException: function not found")
        return LambdaFunctionConfiguration(
            config=LambdaConfig(memory_mb=1024, architecture="arm64", timeout_seconds=30),
            metadata={
                "function_name": function_name,
                "runtime": "python3.11",
                "last_modified": "2026-05-23T00:00:00.000+0000",
            },
        )

    def invoke(self, **kwargs: object) -> None:
        self.invoke_called = True

    def update_function_configuration(self, **kwargs: object) -> None:
        self.mutation_called = True


class FakeCloudWatchClient:
    def __init__(self, *, denied: bool = False, empty: bool = False) -> None:
        self.denied = denied
        self.empty = empty

    def fetch_lambda_metrics(
        self,
        *,
        function_name: str,
        start_time: datetime,
        end_time: datetime,
        period_seconds: int,
    ) -> LambdaCloudWatchMetrics:
        if self.denied:
            raise AwsPermissionError("AccessDenied")
        series = {} if self.empty else {"invocations": _series([1.0])}
        return LambdaCloudWatchMetrics(
            function_name=function_name,
            start_time=start_time,
            end_time=end_time,
            period_seconds=period_seconds,
            series=series,
        )


class FakeLogsClient:
    def __init__(self, *, denied: bool = False) -> None:
        self.denied = denied

    def fetch_lambda_report_logs(self, **kwargs: object) -> list[object]:
        if self.denied:
            raise AwsPermissionError("AccessDenied")
        return []


def test_local_only_doctor_works_without_aws(tmp_path: Path) -> None:
    def fail_factory(**kwargs: object) -> object:
        raise AssertionError("AWS should not be called for local-only doctor")

    result = run_doctor(
        output_dir=tmp_path / "reports",
        deps=DoctorDependencies(
            session_factory=fail_factory,
            lambda_client_factory=fail_factory,
            cloudwatch_client_factory=fail_factory,
            logs_client_factory=fail_factory,
        ),
    )

    assert result.overall_status == "pass"
    assert any(check.status == "skip" for check in result.checks)
    assert "LambdaOpt Doctor" in render_doctor_text(result)


def test_missing_credentials_fails_when_aws_checks_requested(tmp_path: Path) -> None:
    result = run_doctor(
        function_name="my-function",
        output_dir=tmp_path,
        deps=_deps(session_factory=lambda **kwargs: _raise(AwsCredentialsError("missing"))),
    )

    assert result.overall_status == "fail"
    assert any("credentials unavailable" in check.message.lower() for check in result.checks)


def test_sts_identity_success(tmp_path: Path) -> None:
    result = run_doctor(function_name="my-function", output_dir=tmp_path, deps=_deps())

    assert any(
        check.name == "caller_identity" and check.status == "pass" for check in result.checks
    )
    assert "123456789012" in render_doctor_text(result)


def test_lambda_function_found(tmp_path: Path) -> None:
    result = run_doctor(function_name="my-function", output_dir=tmp_path, deps=_deps())

    assert any(check.message == "Function exists: my-function" for check in result.checks)
    assert any(check.message == "Memory: 1024MB" for check in result.checks)
    assert any(check.message == "Architecture: arm64" for check in result.checks)


def test_lambda_function_not_found(tmp_path: Path) -> None:
    result = run_doctor(
        function_name="missing",
        output_dir=tmp_path,
        deps=_deps(lambda_client_factory=lambda **kwargs: FakeLambdaClient(missing=True)),
    )

    assert result.overall_status == "fail"
    assert any("Function check failed" in check.message for check in result.checks)


def test_cloudwatch_permission_denied(tmp_path: Path) -> None:
    result = run_doctor(
        function_name="my-function",
        output_dir=tmp_path,
        deps=_deps(cloudwatch_client_factory=lambda **kwargs: FakeCloudWatchClient(denied=True)),
    )

    assert result.overall_status == "fail"
    assert any("cloudwatch:GetMetricData denied" in check.message for check in result.checks)


def test_cloudwatch_success_empty_data_warns(tmp_path: Path) -> None:
    result = run_doctor(
        function_name="my-function",
        output_dir=tmp_path,
        deps=_deps(cloudwatch_client_factory=lambda **kwargs: FakeCloudWatchClient(empty=True)),
    )

    assert result.overall_status == "warn"
    assert any("no metric data" in check.message for check in result.checks)


def test_logs_permission_denied_with_include_logs_fails(tmp_path: Path) -> None:
    result = run_doctor(
        function_name="my-function",
        include_logs=True,
        output_dir=tmp_path,
        deps=_deps(logs_client_factory=lambda **kwargs: FakeLogsClient(denied=True)),
    )

    assert result.overall_status == "fail"
    assert any("CloudWatch Logs permission denied" in check.message for check in result.checks)


def test_doctor_json_output_is_valid(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    def fake_run_doctor(**kwargs: object) -> object:
        return run_doctor(output_dir=tmp_path, deps=_deps())

    monkeypatch.setattr(cli, "run_doctor", fake_run_doctor)
    result = CliRunner().invoke(cli.app, ["doctor", "--json", "--output", str(tmp_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["overall_status"] == "pass"
    assert isinstance(payload["checks"], list)


def test_no_aws_secrets_appear_in_doctor_output(tmp_path: Path) -> None:
    result = run_doctor(function_name="my-function", output_dir=tmp_path, deps=_deps())
    output = render_doctor_text(result)

    assert "FAKE_AWS_ACCESS_KEY_ID_FOR_TESTING" not in output
    assert "FAKE_AWS_SECRET_ACCESS_KEY_FOR_TESTING" not in output
    assert "session_token" not in output.lower()


def test_doctor_never_calls_lambda_invoke_or_mutation(tmp_path: Path) -> None:
    fake_lambda = FakeLambdaClient()
    result = run_doctor(
        function_name="my-function",
        output_dir=tmp_path,
        deps=_deps(lambda_client_factory=lambda **kwargs: fake_lambda),
    )

    assert result.overall_status == "warn"
    assert not fake_lambda.invoke_called
    assert not fake_lambda.mutation_called
    assert any("lambda:InvokeFunction not verified" in check.message for check in result.checks)


def _deps(
    *,
    session_factory: Callable[..., Any] | None = None,
    lambda_client_factory: Callable[..., Any] | None = None,
    cloudwatch_client_factory: Callable[..., Any] | None = None,
    logs_client_factory: Callable[..., Any] | None = None,
) -> DoctorDependencies:
    return DoctorDependencies(
        session_factory=session_factory or (lambda **kwargs: FakeSession()),
        lambda_client_factory=lambda_client_factory or (lambda **kwargs: FakeLambdaClient()),
        cloudwatch_client_factory=cloudwatch_client_factory
        or (lambda **kwargs: FakeCloudWatchClient()),
        logs_client_factory=logs_client_factory or (lambda **kwargs: FakeLogsClient()),
    )


def _series(values: list[float]) -> MetricSeries:
    start = datetime.now(UTC) - timedelta(minutes=5)
    return MetricSeries(
        label="Invocations",
        points=[
            MetricPoint(timestamp=start + timedelta(minutes=index), value=value)
            for index, value in enumerate(values)
        ],
    )


def _raise(exc: Exception) -> object:
    raise exc
