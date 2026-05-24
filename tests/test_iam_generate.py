import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import lambdaopt.cli as cli
from lambdaopt.iam import IamMode, IamPolicySpec, generate_iam_policy, infer_account_id

ALL_MODES: list[IamMode] = [
    "plan",
    "bench",
    "tune-candidates",
    "analyze",
    "analyze-with-logs",
    "watch-dry-run",
]

MUTATION_ACTIONS = {
    "lambda:UpdateFunctionConfiguration",
    "lambda:PutFunctionConcurrency",
    "lambda:PutProvisionedConcurrencyConfig",
    "lambda:DeleteProvisionedConcurrencyConfig",
}


class FakeSession:
    def client(self, service_name: str) -> "FakeStsClient":
        assert service_name == "sts"
        return FakeStsClient()


class FakeStsClient:
    def get_caller_identity(self) -> dict[str, Any]:
        return {"Account": "123456789012"}


def test_each_mode_generates_expected_actions() -> None:
    expected: dict[IamMode, set[str]] = {
        "plan": {"lambda:GetFunction", "lambda:GetFunctionConfiguration"},
        "bench": {
            "lambda:GetFunction",
            "lambda:GetFunctionConfiguration",
            "lambda:InvokeFunction",
        },
        "tune-candidates": {
            "lambda:GetFunction",
            "lambda:GetFunctionConfiguration",
            "lambda:InvokeFunction",
        },
        "analyze": {
            "lambda:GetFunction",
            "lambda:GetFunctionConfiguration",
            "cloudwatch:GetMetricData",
            "cloudwatch:GetMetricStatistics",
        },
        "analyze-with-logs": {
            "lambda:GetFunction",
            "lambda:GetFunctionConfiguration",
            "cloudwatch:GetMetricData",
            "cloudwatch:GetMetricStatistics",
            "logs:DescribeLogGroups",
            "logs:DescribeLogStreams",
            "logs:FilterLogEvents",
        },
        "watch-dry-run": {
            "lambda:GetFunction",
            "lambda:GetFunctionConfiguration",
            "cloudwatch:GetMetricData",
            "cloudwatch:GetMetricStatistics",
        },
    }

    for mode in ALL_MODES:
        generated = generate_iam_policy(_spec(mode))
        assert expected[mode].issubset(_actions(generated.policy))


def test_watch_dry_run_can_include_logs() -> None:
    generated = generate_iam_policy(_spec("watch-dry-run", include_logs=True))

    assert "logs:FilterLogEvents" in _actions(generated.policy)
    assert "logs:DescribeLogStreams" in _actions(generated.policy)


def test_no_mode_includes_admin_or_mutation_actions() -> None:
    for mode in ALL_MODES:
        actions = _actions(generate_iam_policy(_spec(mode, include_logs=True)).policy)
        assert "AdministratorAccess" not in actions
        assert not MUTATION_ACTIONS.intersection(actions)


def test_lambda_arn_is_scoped_correctly() -> None:
    policy = generate_iam_policy(_spec("plan")).policy

    resources = _resources(policy)
    assert "arn:aws:lambda:us-east-1:123456789012:function:my-function" in resources
    assert "arn:aws:lambda:us-east-1:123456789012:function:my-function:*" in resources


def test_logs_arn_is_scoped_correctly() -> None:
    policy = generate_iam_policy(_spec("analyze-with-logs")).policy

    resources = _resources(policy)
    assert "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/my-function" in resources
    assert "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/my-function:*" in resources


def test_account_id_provided_means_no_aws_call_needed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail_resolver(**kwargs: object) -> str:
        raise AssertionError("STS should not be called when --account-id is provided")

    monkeypatch.setattr(cli, "iam_account_id_resolver", fail_resolver)
    result = CliRunner().invoke(
        cli.app,
        [
            "iam",
            "generate",
            "--mode",
            "plan",
            "--function",
            "my-function",
            "--region",
            "us-east-1",
            "--account-id",
            "123456789012",
            "--json-only",
        ],
    )

    assert result.exit_code == 0


def test_missing_account_id_can_be_inferred_with_mocked_sts() -> None:
    account_id = infer_account_id(session_factory=lambda **kwargs: FakeSession())

    assert account_id == "123456789012"


def test_json_only_outputs_valid_json(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "iam_account_id_resolver", lambda **kwargs: "123456789012")
    result = CliRunner().invoke(
        cli.app,
        [
            "iam",
            "generate",
            "--mode",
            "analyze",
            "--function",
            "my-function",
            "--region",
            "us-east-1",
            "--json-only",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["Version"] == "2012-10-17"


def test_output_writes_policy_file(tmp_path: Path) -> None:
    output_path = tmp_path / "policy.json"
    result = CliRunner().invoke(
        cli.app,
        [
            "iam",
            "generate",
            "--mode",
            "bench",
            "--function",
            "my-function",
            "--region",
            "us-east-1",
            "--account-id",
            "123456789012",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    policy = json.loads(output_path.read_text(encoding="utf-8"))
    assert "lambda:InvokeFunction" in _actions(policy)


def test_invalid_mode_fails_clearly() -> None:
    result = CliRunner().invoke(
        cli.app,
        [
            "iam",
            "generate",
            "--mode",
            "unsafe",
            "--function",
            "my-function",
            "--region",
            "us-east-1",
            "--account-id",
            "123456789012",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid value" in result.output or "invalid choice" in result.output.lower()


def _spec(mode: IamMode, *, include_logs: bool = False) -> IamPolicySpec:
    return IamPolicySpec(
        mode=mode,
        function_name="my-function",
        region="us-east-1",
        account_id="123456789012",
        include_logs=include_logs,
    )


def _actions(policy: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for statement in policy["Statement"]:
        raw_actions = statement["Action"]
        if isinstance(raw_actions, str):
            actions.add(raw_actions)
        else:
            actions.update(raw_actions)
    return actions


def _resources(policy: dict[str, Any]) -> set[str]:
    resources: set[str] = set()
    for statement in policy["Statement"]:
        raw_resources = statement["Resource"]
        if isinstance(raw_resources, str):
            resources.add(raw_resources)
        else:
            resources.update(raw_resources)
    return resources
