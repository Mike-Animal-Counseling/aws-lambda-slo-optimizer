"""Least-privilege IAM policy generation for LambdaOpt usage modes."""

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from lambdaopt.aws.session import create_aws_session
from lambdaopt.exceptions import AwsCredentialsError, AwsIntegrationError, LambdaOptValidationError

IamMode = Literal[
    "plan",
    "bench",
    "tune-candidates",
    "analyze",
    "analyze-with-logs",
    "watch-dry-run",
]

LAMBDA_READ_ACTIONS = ["lambda:GetFunction", "lambda:GetFunctionConfiguration"]
LAMBDA_INVOKE_ACTIONS = ["lambda:InvokeFunction"]
CLOUDWATCH_READ_ACTIONS = ["cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics"]
LOGS_DISCOVERY_ACTIONS = ["logs:DescribeLogGroups"]
LOGS_READ_ACTIONS = ["logs:DescribeLogStreams", "logs:FilterLogEvents"]
MUTATION_ACTIONS = {
    "lambda:UpdateFunctionConfiguration",
    "lambda:PutFunctionConcurrency",
    "lambda:PutProvisionedConcurrencyConfig",
    "lambda:DeleteProvisionedConcurrencyConfig",
}
ADMIN_ACTION = "AdministratorAccess"


class StsClient(Protocol):
    """Subset of STS used for account-id inference."""

    def get_caller_identity(self) -> dict[str, Any]:
        """Return caller identity metadata."""


class AwsSession(Protocol):
    """Subset of boto3 Session used for account-id inference."""

    def client(self, service_name: str) -> StsClient:
        """Create a service client."""


@dataclass(frozen=True)
class IamPolicySpec:
    """Inputs for generating a LambdaOpt IAM policy."""

    mode: IamMode
    function_name: str
    region: str
    account_id: str
    include_logs: bool = False


@dataclass(frozen=True)
class GeneratedIamPolicy:
    """Generated policy plus user-facing explanations."""

    mode: IamMode
    policy: dict[str, Any]
    explanations: list[str]
    mutates_aws: bool = False
    safety_notes: tuple[str, ...] = (
        "This policy does not grant AdministratorAccess.",
        "This policy does not grant Lambda configuration or provisioned concurrency mutation.",
        "LambdaOpt uses boto3's standard credential provider chain.",
    )

    def to_json(self) -> str:
        """Serialize the policy document as pretty JSON."""
        return json.dumps(self.policy, indent=2, sort_keys=False) + "\n"


def infer_account_id(
    *,
    profile: str | None = None,
    region: str | None = None,
    session_factory: Any = create_aws_session,
) -> str:
    """Infer the AWS account id with STS GetCallerIdentity."""
    try:
        session: AwsSession = session_factory(profile=profile, region=region)
        identity = session.client("sts").get_caller_identity()
    except NoCredentialsError as exc:
        raise AwsCredentialsError(
            "AWS credentials were not found. Pass --account-id or configure AWS credentials."
        ) from exc
    except (BotoCoreError, ClientError) as exc:
        raise AwsIntegrationError(f"Could not infer AWS account id with STS: {exc}") from exc

    account_id = identity.get("Account")
    if not isinstance(account_id, str) or not account_id:
        raise AwsIntegrationError("STS GetCallerIdentity did not return an account id.")
    return account_id


def generate_iam_policy(spec: IamPolicySpec) -> GeneratedIamPolicy:
    """Generate a least-privilege IAM policy for a LambdaOpt usage mode."""
    _validate_spec(spec)
    lambda_resources = _lambda_resources(spec.region, spec.account_id, spec.function_name)
    statements: list[dict[str, Any]] = [
        {
            "Sid": "ReadLambdaFunctionMetadata",
            "Effect": "Allow",
            "Action": LAMBDA_READ_ACTIONS,
            "Resource": lambda_resources,
        }
    ]
    explanations = [
        "lambda:GetFunction and lambda:GetFunctionConfiguration read Lambda metadata only."
    ]

    if spec.mode in {"bench", "tune-candidates"}:
        statements.append(
            {
                "Sid": "InvokeApprovedLambdaFunctions",
                "Effect": "Allow",
                "Action": LAMBDA_INVOKE_ACTIONS,
                "Resource": lambda_resources,
            }
        )
        explanations.append(
            "lambda:InvokeFunction is required for bench and candidate benchmarking; "
            "it invokes function code but does not change configuration."
        )

    include_cloudwatch = spec.mode in {"analyze", "analyze-with-logs", "watch-dry-run"}
    if include_cloudwatch:
        statements.append(
            {
                "Sid": "ReadLambdaCloudWatchMetrics",
                "Effect": "Allow",
                "Action": CLOUDWATCH_READ_ACTIONS,
                "Resource": "*",
            }
        )
        explanations.append(
            'CloudWatch metric read actions use Resource "*" because CloudWatch metrics '
            "APIs do not support Lambda function-level resource scoping."
        )

    include_logs = spec.mode == "analyze-with-logs" or (
        spec.mode == "watch-dry-run" and spec.include_logs
    )
    if include_logs:
        statements.extend(
            [
                {
                    "Sid": "DiscoverLambdaLogGroups",
                    "Effect": "Allow",
                    "Action": LOGS_DISCOVERY_ACTIONS,
                    "Resource": "*",
                },
                {
                    "Sid": "ReadLambdaReportLogs",
                    "Effect": "Allow",
                    "Action": LOGS_READ_ACTIONS,
                    "Resource": _logs_resources(
                        spec.region,
                        spec.account_id,
                        spec.function_name,
                    ),
                },
            ]
        )
        explanations.append(
            "CloudWatch Logs permissions are scoped to the Lambda log group where possible."
        )

    policy = {"Version": "2012-10-17", "Statement": statements}
    _assert_policy_is_safe(policy)
    return GeneratedIamPolicy(mode=spec.mode, policy=policy, explanations=explanations)


def render_iam_policy_output(generated: GeneratedIamPolicy) -> str:
    """Render human-readable IAM generation output."""
    lines = [
        "LambdaOpt IAM Policy",
        "",
        f"Mode: {generated.mode}",
        "Mutates AWS resources: no",
        "",
        "Policy JSON:",
        generated.to_json().rstrip(),
        "",
        "Permission explanations:",
    ]
    lines.extend(f"- {explanation}" for explanation in generated.explanations)
    lines.extend(["", "Safety notes:"])
    lines.extend(f"- {note}" for note in generated.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _lambda_resources(region: str, account_id: str, function_name: str) -> list[str]:
    base = f"arn:aws:lambda:{region}:{account_id}:function:{function_name}"
    return [base, f"{base}:*"]


def _logs_resources(region: str, account_id: str, function_name: str) -> list[str]:
    log_group = f"/aws/lambda/{function_name}"
    base = f"arn:aws:logs:{region}:{account_id}:log-group:{log_group}"
    return [base, f"{base}:*"]


def _validate_spec(spec: IamPolicySpec) -> None:
    if not spec.function_name.strip():
        raise LambdaOptValidationError("Function name is required.")
    if not spec.region.strip():
        raise LambdaOptValidationError("Region is required.")
    if not spec.account_id.isdigit() or len(spec.account_id) != 12:
        raise LambdaOptValidationError("Account id must be a 12-digit AWS account id.")


def _assert_policy_is_safe(policy: dict[str, Any]) -> None:
    actions = _flatten_actions(policy)
    unsafe = sorted(MUTATION_ACTIONS.intersection(actions))
    if unsafe:
        raise LambdaOptValidationError(
            f"Generated policy unexpectedly included mutation actions: {', '.join(unsafe)}"
        )
    if ADMIN_ACTION in actions:
        raise LambdaOptValidationError(
            "Generated policy unexpectedly included AdministratorAccess."
        )


def _flatten_actions(policy: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for statement in policy.get("Statement", []):
        raw_actions = statement.get("Action", [])
        if isinstance(raw_actions, str):
            actions.add(raw_actions)
        else:
            actions.update(str(action) for action in raw_actions)
    return actions
