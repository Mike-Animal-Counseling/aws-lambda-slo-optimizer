import json
from pathlib import Path

from typer.testing import CliRunner

from lambdaopt.analysis.cost_model import estimate_lambda_cost
from lambdaopt.analysis.latency import calculate_latency_stats
from lambdaopt.cli import app
from lambdaopt.models import AnalyzedConfig, BenchmarkResult, LambdaConfig, Recommendation
from lambdaopt.report.json_output import write_benchmark_results_json, write_recommendation_json
from lambdaopt.report.markdown import write_markdown_report
from lambdaopt.security import payload_metadata

FAKE_ACCESS_KEY = "FAKE_AWS_ACCESS_KEY_ID_FOR_TESTING"
FAKE_SECRET_KEY = "FAKE_AWS_SECRET_ACCESS_KEY_FOR_TESTING"
FAKE_PAYLOAD_SECRET = "FAKE_PAYLOAD_SECRET_FOR_TESTING"


def test_generated_reports_redact_metadata_and_payload_secrets(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"token": FAKE_PAYLOAD_SECRET}), encoding="utf-8")
    latency = calculate_latency_stats([100, 120, 140], target_ms=500)
    analyzed = AnalyzedConfig(
        config=LambdaConfig(memory_mb=512, architecture="x86_64"),
        latency=latency,
        cost=estimate_lambda_cost(
            memory_mb=512,
            avg_duration_ms=latency.mean_ms,
            monthly_requests=1000,
            architecture="x86_64",
        ),
        cold_start_rate=0,
        slo_passed=True,
        metadata={
            "aws_access_key_id": FAKE_ACCESS_KEY,
            "nested": {"aws_secret_access_key": FAKE_SECRET_KEY},
            "payload": payload_metadata(payload_path),
        },
    )
    recommendation = Recommendation(
        recommended_config=analyzed.config,
        reason_summary=f"token={FAKE_PAYLOAD_SECRET}",
        rejected_reasons={},
        warnings=[f"aws_secret_access_key={FAKE_SECRET_KEY}"],
        alternatives=[analyzed],
        confidence=0.9,
    )

    write_benchmark_results_json([analyzed], tmp_path)
    write_recommendation_json(recommendation, tmp_path)
    write_markdown_report(
        analyzed_configs=[analyzed],
        recommendation=recommendation,
        target_p95_ms=500,
        monthly_requests=1000,
        output_dir=tmp_path,
        warnings=[f"aws_access_key_id={FAKE_ACCESS_KEY}"],
    )

    report_names = {
        "benchmark_results.json",
        "recommended_config.json",
        "optimization_report.md",
    }
    combined = "\n".join((tmp_path / name).read_text(encoding="utf-8") for name in report_names)

    assert FAKE_ACCESS_KEY not in combined
    assert FAKE_SECRET_KEY not in combined
    assert FAKE_PAYLOAD_SECRET not in combined
    assert "sha256" in combined
    assert "payload.json" in combined


def test_cli_help_does_not_expose_direct_credential_options() -> None:
    help_commands = [
        ["--help"],
        ["tune", "--help"],
        ["doctor", "--help"],
        ["iam", "generate", "--help"],
    ]

    for command in help_commands:
        result = CliRunner().invoke(app, command)

        assert result.exit_code == 0
        assert "--access-key" not in result.output
        assert "--secret-key" not in result.output
        assert "--session-token" not in result.output
        assert "--aws-access-key-id" not in result.output
        assert "--aws-secret-access-key" not in result.output


def test_github_actions_do_not_reference_aws_secrets() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in Path(".github/workflows").glob("*.yml")
    )

    assert "AWS_ACCESS_KEY_ID" not in workflow_text
    assert "AWS_SECRET_ACCESS_KEY" not in workflow_text
    assert "AWS_SESSION_TOKEN" not in workflow_text
    assert "${{ secrets" not in workflow_text


def test_benchmark_result_payload_metadata_excludes_raw_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"secret": FAKE_PAYLOAD_SECRET}), encoding="utf-8")

    result = BenchmarkResult(
        config=LambdaConfig(memory_mb=512, architecture="x86_64"),
        raw_latencies_ms=[100],
        metadata={"payload": payload_metadata(payload_path)},
    )

    serialized = json.dumps(result.model_dump(mode="json"))

    assert FAKE_PAYLOAD_SECRET not in serialized
    assert "size_bytes" in serialized
    assert "sha256" in serialized
