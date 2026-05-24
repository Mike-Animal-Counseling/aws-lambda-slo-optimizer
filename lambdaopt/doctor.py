"""Read-only environment and AWS readiness checks for LambdaOpt."""

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from lambdaopt import __version__
from lambdaopt.aws.cloudwatch_client import CloudWatchClient
from lambdaopt.aws.lambda_client import LambdaClient
from lambdaopt.aws.logs_client import LogsClient
from lambdaopt.aws.session import create_aws_session
from lambdaopt.exceptions import (
    AwsCredentialsError,
    AwsIntegrationError,
    AwsPermissionError,
    LambdaOptConfigError,
)
from lambdaopt.security import redact_value

CheckStatus = Literal["pass", "warn", "fail", "skip"]
OverallStatus = Literal["pass", "warn", "fail"]


class StsClient(Protocol):
    """Subset of STS client methods used by doctor."""

    def get_caller_identity(self) -> dict[str, Any]:
        """Return caller identity."""


class AwsSession(Protocol):
    """Subset of boto3 Session methods used by doctor."""

    region_name: str | None

    def client(self, service_name: str) -> StsClient:
        """Create a service client."""


class DoctorCheck(BaseModel):
    """One doctor check result."""

    model_config = ConfigDict(frozen=True)

    category: str
    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DoctorResult(BaseModel):
    """Structured doctor command output."""

    model_config = ConfigDict(frozen=True)

    overall_status: OverallStatus
    checks: list[DoctorCheck]

    @property
    def exit_code(self) -> int:
        """Return process exit code for this result."""
        return 1 if self.overall_status == "fail" else 0


@dataclass(frozen=True)
class DoctorDependencies:
    """External dependencies for doctor checks."""

    session_factory: Callable[..., Any] = create_aws_session
    lambda_client_factory: Callable[..., Any] = LambdaClient.from_session_options
    cloudwatch_client_factory: Callable[..., Any] = CloudWatchClient.from_session_options
    logs_client_factory: Callable[..., Any] = LogsClient.from_session_options


@dataclass
class _DoctorContext:
    function_name: str | None
    region: str | None
    profile: str | None
    output_dir: Path
    include_logs: bool
    deps: DoctorDependencies
    checks: list[DoctorCheck] = field(default_factory=list)
    resolved_region: str | None = None


def run_doctor(
    *,
    function_name: str | None = None,
    region: str | None = None,
    profile: str | None = None,
    output_dir: Path = Path("reports"),
    include_logs: bool = False,
    deps: DoctorDependencies | None = None,
) -> DoctorResult:
    """Run local and optional AWS readiness checks without mutating AWS resources."""
    context = _DoctorContext(
        function_name=function_name,
        region=region,
        profile=profile,
        output_dir=output_dir,
        include_logs=include_logs,
        deps=deps or DoctorDependencies(),
    )

    _check_environment(context)
    if function_name is None:
        _add_aws_skips(context)
    else:
        _check_aws_identity(context)
        _check_lambda_function(context)
        _check_invoke_permission_notice(context)
        _check_cloudwatch_metrics(context)
        _check_logs(context)
    _check_safety(context)

    return DoctorResult(
        overall_status=_overall_status(context.checks),
        checks=context.checks,
    )


def render_doctor_text(result: DoctorResult) -> str:
    """Render human-readable doctor output."""
    lines = ["LambdaOpt Doctor", ""]
    categories = [
        ("environment", "Environment"),
        ("aws_identity", "AWS Identity"),
        ("lambda", "Lambda Function"),
        ("permissions", "Permissions"),
        ("cloudwatch", "CloudWatch"),
        ("logs", "CloudWatch Logs"),
        ("safety", "Safety"),
    ]
    for category, title in categories:
        checks = [check for check in result.checks if check.category == category]
        if not checks:
            continue
        lines.append(title)
        for check in checks:
            lines.append(f"{check.status.upper():<5} {check.message}")
        lines.append("")

    label = {
        "pass": "READY",
        "warn": "READY WITH WARNINGS",
        "fail": "NOT READY",
    }[result.overall_status]
    lines.extend(["Result", label, ""])
    return "\n".join(lines)


def _check_environment(context: _DoctorContext) -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    _add(context, "environment", "python_version", "pass", f"Python version: {version}")
    _add(context, "environment", "lambdaopt_version", "pass", f"LambdaOpt version: {__version__}")
    _add(context, "environment", "cwd", "pass", f"Current working directory: {Path.cwd()}")
    _check_output_directory(context)
    config_path = Path("lambdaopt.yaml")
    if config_path.exists():
        _add(context, "environment", "config_file", "pass", f"Config file detected: {config_path}")
    else:
        _add(context, "environment", "config_file", "skip", "Config file not detected.")


def _check_output_directory(context: _DoctorContext) -> None:
    try:
        context.output_dir.mkdir(parents=True, exist_ok=True)
        probe = context.output_dir / ".lambdaopt-doctor-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise LambdaOptConfigError(
            f"Output directory is not writable: {context.output_dir}"
        ) from exc
    _add(
        context,
        "environment",
        "output_dir",
        "pass",
        f"Output directory writable: {context.output_dir}",
    )


def _add_aws_skips(context: _DoctorContext) -> None:
    _add(
        context,
        "aws_identity",
        "aws_identity",
        "skip",
        "AWS identity not checked because FUNCTION_NAME was not provided.",
    )
    _add(
        context,
        "lambda",
        "function",
        "skip",
        "Lambda function checks skipped because FUNCTION_NAME was not provided.",
    )
    _add(
        context,
        "cloudwatch",
        "metrics",
        "skip",
        "CloudWatch metrics not checked because FUNCTION_NAME was not provided.",
    )
    _add(
        context,
        "logs",
        "logs",
        "skip",
        "CloudWatch Logs not checked. Use FUNCTION_NAME and --include-logs.",
    )


def _check_aws_identity(context: _DoctorContext) -> None:
    try:
        session = context.deps.session_factory(profile=context.profile, region=context.region)
        context.resolved_region = context.region or session.region_name
        identity = session.client("sts").get_caller_identity()
    except AwsCredentialsError as exc:
        _add(context, "aws_identity", "credentials", "fail", f"AWS credentials unavailable: {exc}")
        return
    except Exception as exc:
        _add(context, "aws_identity", "identity", "fail", f"Caller identity check failed: {exc}")
        return

    _add(context, "aws_identity", "credentials", "pass", "AWS credentials found.")
    _add(
        context,
        "aws_identity",
        "caller_identity",
        "pass",
        f"Caller identity: {identity.get('Arn', 'unknown')}",
        {"account_id": identity.get("Account"), "arn": identity.get("Arn")},
    )
    if context.resolved_region:
        _add(context, "aws_identity", "region", "pass", f"Region: {context.resolved_region}")
    else:
        _add(context, "aws_identity", "region", "warn", "Region was not resolved.")


def _check_lambda_function(context: _DoctorContext) -> None:
    if context.function_name is None:
        return
    try:
        client = context.deps.lambda_client_factory(profile=context.profile, region=context.region)
        function = client.get_function_configuration(context.function_name)
    except AwsPermissionError as exc:
        _add(
            context,
            "permissions",
            "lambda_get_config",
            "fail",
            f"lambda:GetFunctionConfiguration denied: {exc}",
        )
        return
    except AwsCredentialsError as exc:
        _add(context, "lambda", "function", "fail", f"AWS credentials unavailable: {exc}")
        return
    except AwsIntegrationError as exc:
        _add(context, "lambda", "function", "fail", f"Function check failed: {exc}")
        return

    config = function.config
    metadata = function.metadata
    _add(
        context,
        "lambda",
        "function",
        "pass",
        f"Function exists: {metadata.get('function_name', context.function_name)}",
    )
    _add(context, "permissions", "lambda_get_config", "pass", "lambda:GetFunctionConfiguration")
    if runtime := metadata.get("runtime"):
        _add(context, "lambda", "runtime", "pass", f"Runtime: {runtime}")
    _add(context, "lambda", "memory", "pass", f"Memory: {config.memory_mb}MB")
    _add(context, "lambda", "architecture", "pass", f"Architecture: {config.architecture}")
    _add(context, "lambda", "timeout", "pass", f"Timeout: {config.timeout_seconds}s")
    if last_modified := metadata.get("last_modified"):
        _add(context, "lambda", "last_modified", "pass", f"Last modified: {last_modified}")


def _check_invoke_permission_notice(context: _DoctorContext) -> None:
    _add(
        context,
        "permissions",
        "lambda_invoke",
        "warn",
        "lambda:InvokeFunction not verified by doctor. bench/tune requires it.",
    )


def _check_cloudwatch_metrics(context: _DoctorContext) -> None:
    if context.function_name is None:
        return
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=1)
    try:
        client = context.deps.cloudwatch_client_factory(
            profile=context.profile, region=context.region
        )
        metrics = client.fetch_lambda_metrics(
            function_name=context.function_name,
            start_time=start_time,
            end_time=end_time,
            period_seconds=300,
        )
    except AwsPermissionError as exc:
        _add(context, "cloudwatch", "metrics", "fail", f"cloudwatch:GetMetricData denied: {exc}")
        return
    except AwsCredentialsError as exc:
        _add(context, "cloudwatch", "metrics", "fail", f"AWS credentials unavailable: {exc}")
        return
    except AwsIntegrationError as exc:
        _add(context, "cloudwatch", "metrics", "fail", f"CloudWatch metrics check failed: {exc}")
        return

    datapoints = sum(len(series.points) for series in metrics.series.values())
    if datapoints:
        _add(
            context,
            "cloudwatch",
            "metrics",
            "pass",
            "cloudwatch:GetMetricData succeeded and metric data was found.",
            {"datapoints": datapoints},
        )
    else:
        _add(
            context,
            "cloudwatch",
            "metrics",
            "warn",
            "cloudwatch:GetMetricData succeeded but no metric data was found.",
        )


def _check_logs(context: _DoctorContext) -> None:
    if context.function_name is None:
        return
    if not context.include_logs:
        _add(context, "logs", "logs", "warn", "CloudWatch Logs not checked. Use --include-logs.")
        return

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=1)
    try:
        client = context.deps.logs_client_factory(profile=context.profile, region=context.region)
        logs = client.fetch_lambda_report_logs(
            function_name=context.function_name,
            start_time=start_time,
            end_time=end_time,
            limit=10,
        )
    except AwsPermissionError as exc:
        _add(context, "logs", "logs", "fail", f"CloudWatch Logs permission denied: {exc}")
        return
    except AwsCredentialsError as exc:
        _add(context, "logs", "logs", "fail", f"AWS credentials unavailable: {exc}")
        return
    except AwsIntegrationError as exc:
        message = str(exc)
        status: CheckStatus = "warn" if "ResourceNotFound" in message else "fail"
        _add(context, "logs", "logs", status, f"CloudWatch Logs check failed: {message}")
        return

    if logs:
        _add(context, "logs", "logs", "pass", "CloudWatch Logs query succeeded.")
    else:
        _add(
            context,
            "logs",
            "logs",
            "warn",
            "CloudWatch Logs query succeeded but no REPORT logs were found.",
        )


def _check_safety(context: _DoctorContext) -> None:
    _add(
        context,
        "safety",
        "no_key_cli_args",
        "pass",
        "No AWS key material is required as CLI args.",
    )
    _add(
        context,
        "safety",
        "boto3_provider_chain",
        "pass",
        "LambdaOpt uses the standard boto3 provider chain.",
    )
    _add(context, "safety", "no_mutation", "pass", "No production mutation is performed by doctor.")
    _add(
        context,
        "safety",
        "safe_report_outputs",
        "pass",
        "AWS key material must not be written to reports/logs.",
    )


def _overall_status(checks: list[DoctorCheck]) -> OverallStatus:
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "warn" for check in checks):
        return "warn"
    return "pass"


def _add(
    context: _DoctorContext,
    category: str,
    name: str,
    status: CheckStatus,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    context.checks.append(
        DoctorCheck(
            category=category,
            name=name,
            status=status,
            message=message,
            details=redact_value(details or {}),
        )
    )
