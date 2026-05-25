from pathlib import Path
from typing import Literal

from typer.testing import CliRunner

import lambdaopt.cli as cli
from lambdaopt.doctor import DoctorCheck, DoctorResult


def test_start_without_function_creates_first_report(tmp_path: Path) -> None:
    output_dir = tmp_path / "start"

    result = CliRunner().invoke(
        cli.app,
        [
            "start",
            "--p95",
            "500",
            "--monthly-requests",
            "1000000",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "LambdaOpt Start" in result.output
    assert "Demo optimization completed" in result.output
    assert (output_dir / "optimization_report.md").exists()
    assert (output_dir / "recommended_config.json").exists()


def test_start_with_function_runs_doctor_only_by_default(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    analyze_called = False

    def fake_run_doctor(**kwargs: object) -> DoctorResult:
        return _doctor_result("warn")

    def fake_analyze(**kwargs: object) -> object:
        nonlocal analyze_called
        analyze_called = True
        raise AssertionError("start should not run analyze unless --run-analyze is provided")

    monkeypatch.setattr(cli, "run_doctor", fake_run_doctor)
    monkeypatch.setattr(cli, "_run_cloudwatch_analysis_workflow", fake_analyze)

    result = CliRunner().invoke(
        cli.app,
        [
            "start",
            "my-function",
            "--region",
            "us-east-1",
            "--p95",
            "500",
            "--output",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert not analyze_called
    assert "READY WITH WARNINGS" in result.output
    assert "lambdaopt analyze my-function" in result.output
    assert "does not invoke Lambda or mutate AWS" in result.output


def test_start_with_failed_doctor_suggests_iam_policy(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    def fake_run_doctor(**kwargs: object) -> DoctorResult:
        return _doctor_result("fail")

    monkeypatch.setattr(cli, "run_doctor", fake_run_doctor)

    result = CliRunner().invoke(
        cli.app,
        [
            "start",
            "my-function",
            "--region",
            "us-east-1",
            "--include-logs",
            "--output",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1, result.output
    assert "NOT READY" in result.output
    assert "lambdaopt iam generate --mode analyze-with-logs" in result.output
    assert "AdministratorAccess" not in result.output


def test_start_run_analyze_calls_analysis_after_readiness(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, object]] = []

    def fake_run_doctor(**kwargs: object) -> DoctorResult:
        return _doctor_result("pass")

    def fake_analyze(**kwargs: object) -> object:
        calls.append(kwargs)
        return type("Analysis", (), {"slo_passed": True})()

    monkeypatch.setattr(cli, "run_doctor", fake_run_doctor)
    monkeypatch.setattr(cli, "_run_cloudwatch_analysis_workflow", fake_analyze)

    result = CliRunner().invoke(
        cli.app,
        [
            "start",
            "my-function",
            "--region",
            "us-east-1",
            "--p95",
            "500",
            "--run-analyze",
            "--output",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls
    assert calls[0]["function_name"] == "my-function"
    assert calls[0]["target_p95_ms"] == 500
    assert "CloudWatch analysis completed" in result.output


def test_help_surfaces_start_here_panel() -> None:
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "Start here" in result.output
    assert "start" in result.output


def _doctor_result(status: Literal["pass", "warn", "fail"]) -> DoctorResult:
    checks = [
        DoctorCheck(
            category="aws_identity",
            name="credentials",
            status="pass" if status != "fail" else "fail",
            message=(
                "AWS credentials found." if status != "fail" else "AWS credentials unavailable."
            ),
        ),
        DoctorCheck(
            category="lambda",
            name="function",
            status="pass" if status != "fail" else "skip",
            message="Function exists: my-function" if status != "fail" else "Function not checked.",
        ),
        DoctorCheck(
            category="cloudwatch",
            name="metrics",
            status="warn" if status == "warn" else ("pass" if status == "pass" else "fail"),
            message=(
                "cloudwatch:GetMetricData succeeded but no metric data was found."
                if status == "warn"
                else "cloudwatch:GetMetricData succeeded."
                if status == "pass"
                else "cloudwatch:GetMetricData denied."
            ),
        ),
    ]
    return DoctorResult(overall_status=status, checks=checks)
