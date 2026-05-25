"""Command-line interface for LambdaOpt."""

import json
import traceback
from pathlib import Path
from typing import Annotated, Literal, NoReturn

import typer

from lambdaopt.analysis.cloudwatch_analysis import CloudWatchAnalysis, analyze_cloudwatch_metrics
from lambdaopt.analysis.cold_start import analyze_cold_starts_from_messages
from lambdaopt.analysis.cost_model import estimate_lambda_cost
from lambdaopt.analysis.latency import calculate_latency_stats
from lambdaopt.analysis.pareto import mark_pareto_frontier
from lambdaopt.analysis.risk import assess_config_risk
from lambdaopt.aws.cloudwatch_client import CloudWatchClient, LambdaCloudWatchMetrics, parse_window
from lambdaopt.aws.lambda_client import LambdaClient
from lambdaopt.aws.logs_client import LogsClient
from lambdaopt.benchmark.candidate_runner import (
    SEPARATE_TEST_FUNCTIONS_SAFETY_NOTE,
    load_candidate_function_mappings,
    run_candidate_function_benchmarks,
)
from lambdaopt.benchmark.candidate_schema import (
    CandidateMappings,
    candidate_validation_warnings,
)
from lambdaopt.benchmark.plan import BenchmarkPlan, create_benchmark_plan
from lambdaopt.benchmark.result_collector import CLIENT_OBSERVED_DURATION_WARNING
from lambdaopt.benchmark.runner import CURRENT_CONFIG_ONLY_WARNING, run_current_config_benchmark
from lambdaopt.config import LambdaOptConfig, get_version, load_benchmark_results, load_config
from lambdaopt.dashboard.app import launch_dashboard
from lambdaopt.doctor import DoctorCheck, DoctorResult, render_doctor_text, run_doctor
from lambdaopt.exceptions import LambdaOptConfigError, LambdaOptError, LambdaOptSafetyError
from lambdaopt.iam import (
    IamMode,
    IamPolicySpec,
    generate_iam_policy,
    infer_account_id,
    render_iam_policy_output,
)
from lambdaopt.logging_config import configure_logging
from lambdaopt.models import AnalyzedConfig, BenchmarkResult, Recommendation
from lambdaopt.recommend.controller import ControllerInput, evaluate_controller
from lambdaopt.recommend.slo_recommender import recommend_cheapest_slo_config
from lambdaopt.report.charts import write_cost_vs_p95_chart
from lambdaopt.report.cloudwatch_markdown import write_cloudwatch_analysis_report
from lambdaopt.report.json_output import (
    write_benchmark_results_json,
    write_recommendation_json,
)
from lambdaopt.report.markdown import write_markdown_report
from lambdaopt.security import redact_text, redact_value
from lambdaopt.simulator.generator import DEFAULT_SAMPLE_COUNT, DEFAULT_SEED
from lambdaopt.simulator.replay import replay_workload
from lambdaopt.simulator.workloads import WorkloadName

DEFAULT_MONTHLY_PROVISIONED_CONCURRENCY_HOURS = 730.0

app = typer.Typer(
    name="lambdaopt",
    help="SLO-aware AWS Lambda deployment optimizer.",
    no_args_is_help=True,
)
iam_app = typer.Typer(help="Generate least-privilege IAM policies.", no_args_is_help=True)
app.add_typer(iam_app, name="iam", rich_help_panel="Advanced")

lambda_client_factory = LambdaClient.from_session_options
cloudwatch_client_factory = CloudWatchClient.from_session_options
logs_client_factory = LogsClient.from_session_options
current_config_benchmark_runner = run_current_config_benchmark
candidate_function_benchmark_runner = run_candidate_function_benchmarks
iam_account_id_resolver = infer_account_id
cli_config = LambdaOptConfig()
debug_mode = False


@app.callback()
def main(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to lambdaopt.yaml.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Enable verbose logging."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Only show warnings and errors in logs."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show traceback details for LambdaOpt errors."),
    ] = False,
) -> None:
    """SLO-aware AWS Lambda deployment optimizer."""
    global cli_config, debug_mode

    debug_mode = debug
    configure_logging(verbose=verbose, quiet=quiet)
    try:
        cli_config = load_config(config_path)
    except LambdaOptError as exc:
        _handle_cli_error(exc)


@app.command(rich_help_panel="Start here")
def version(
    plain: Annotated[
        bool,
        typer.Option("--plain", help="Print only the version number."),
    ] = False,
) -> None:
    """Print the LambdaOpt version."""
    current_version = get_version()
    if plain:
        typer.echo(current_version)
        return

    typer.echo(f"LambdaOpt {current_version}")


@app.command(rich_help_panel="Start here")
def start(
    function_name: Annotated[
        str | None,
        typer.Argument(help="Optional Lambda function name or ARN for AWS readiness checks."),
    ] = None,
    p95: Annotated[
        float,
        typer.Option("--p95", min=0.0, help="Target p95 latency in ms."),
    ] = 500,
    monthly_requests: Annotated[
        int,
        typer.Option("--monthly-requests", min=0, help="Monthly request count for estimates."),
    ] = 1_000_000,
    output_dir: Annotated[
        Path,
        typer.Option("--output", help="Directory where the first report will be written."),
    ] = Path("reports/start"),
    region: Annotated[str | None, typer.Option("--region", help="AWS region.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="AWS profile name.")] = None,
    include_logs: Annotated[
        bool,
        typer.Option("--include-logs", help="Include CloudWatch Logs checks/analysis."),
    ] = False,
    run_analyze: Annotated[
        bool,
        typer.Option(
            "--run-analyze",
            help=(
                "Run CloudWatch analyze after readiness checks pass. "
                "Default only prints next steps."
            ),
        ),
    ] = False,
    window: Annotated[
        str,
        typer.Option("--window", help="CloudWatch window used with --run-analyze."),
    ] = "24h",
) -> None:
    """Guided first-run workflow for local demo or safe AWS readiness."""
    try:
        if function_name is None:
            recommendation = _run_start_local_demo(
                target_p95_ms=p95,
                monthly_requests=monthly_requests,
                output_dir=output_dir,
            )
            _print_start_local_summary(recommendation, p95, output_dir)
            return

        effective_region = _resolve_region(region)
        effective_profile = _resolve_profile(profile)
        result = run_doctor(
            function_name=function_name,
            region=effective_region,
            profile=effective_profile,
            output_dir=output_dir,
            include_logs=include_logs,
        )
        if run_analyze and result.overall_status != "fail":
            analysis_status = _run_cloudwatch_analysis_workflow(
                function_name=function_name,
                window=window,
                target_p95_ms=p95,
                region=effective_region,
                profile=effective_profile,
                monthly_requests=monthly_requests,
                include_logs=include_logs,
                output_dir=output_dir,
            )
            _print_start_analyze_summary(
                function_name=function_name,
                window=window,
                output_dir=output_dir,
                analysis_status=analysis_status,
            )
            raise typer.Exit(0)

        _print_start_aws_summary(
            function_name=function_name,
            target_p95_ms=p95,
            region=effective_region,
            output_dir=output_dir,
            doctor_result=result,
            include_logs=include_logs,
        )
        raise typer.Exit(result.exit_code)
    except LambdaOptError as exc:
        _handle_cli_error(exc)


@app.command(rich_help_panel="Start here")
def quickstart(
    function_name: Annotated[
        str | None,
        typer.Argument(help="Optional Lambda function name for AWS next-step examples."),
    ] = None,
    p95: Annotated[
        float,
        typer.Option("--p95", min=0.0, help="Example p95 latency target in ms."),
    ] = 500,
    region: Annotated[
        str,
        typer.Option("--region", help="Example AWS region for AWS commands."),
    ] = "us-east-1",
) -> None:
    """Print the shortest safe path from first run to a LambdaOpt report."""
    name = function_name or "my-function"
    typer.echo("LambdaOpt Quickstart")
    typer.echo("")
    typer.echo("Best first command:")
    typer.echo("  lambdaopt start")
    typer.echo("")
    typer.echo("Without AWS credentials:")
    typer.echo(f"  lambdaopt start --p95 {p95:g} --output reports/start")
    typer.echo(
        "  lambdaopt tune --input examples/sample_results.json "
        f"--p95 {p95:g} --monthly-requests 1000000 --output reports/sample"
    )
    typer.echo("")
    typer.echo("When you have a sandbox or non-production Lambda:")
    typer.echo(f"  lambdaopt start {name} --region {region} --p95 {p95:g}")
    typer.echo(f"  lambdaopt doctor {name} --region {region}")
    typer.echo(
        "  lambdaopt iam generate --mode analyze-with-logs "
        f"--function {name} --region {region} --account-id ACCOUNT_ID"
    )
    typer.echo(f"  lambdaopt plan {name} --p95 {p95:g} --region {region}")
    typer.echo(
        f"  lambdaopt analyze {name} --window 24h --p95 {p95:g} "
        f"--region {region} --output reports/analyze"
    )
    typer.echo("")
    typer.echo("Reports to open:")
    typer.echo("  reports/start/optimization_report.md")
    typer.echo("  reports/sample/optimization_report.md")
    typer.echo("")
    typer.echo("Safety: LambdaOpt does not mutate production Lambda configuration by default.")


@iam_app.command("generate")
def iam_generate(
    mode: Annotated[
        IamMode,
        typer.Option("--mode", help="LambdaOpt usage mode to generate a policy for."),
    ],
    function_name: Annotated[
        str,
        typer.Option("--function", help="Lambda function name to scope the policy to."),
    ],
    region: Annotated[str, typer.Option("--region", help="AWS region for resource ARNs.")],
    account_id: Annotated[
        str | None,
        typer.Option(
            "--account-id",
            help="AWS account id. If omitted, LambdaOpt tries STS GetCallerIdentity.",
        ),
    ] = None,
    include_logs: Annotated[
        bool,
        typer.Option(
            "--include-logs",
            help="Include CloudWatch Logs permissions for watch-dry-run policies.",
        ),
    ] = False,
    json_only: Annotated[
        bool,
        typer.Option("--json-only", help="Print only the IAM policy JSON."),
    ] = False,
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="Write the generated policy JSON to this file."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="AWS profile used only when --account-id is omitted.",
        ),
    ] = None,
) -> None:
    """Generate least-privilege IAM policy JSON for LambdaOpt commands."""
    try:
        resolved_account_id = account_id or iam_account_id_resolver(
            profile=_resolve_profile(profile),
            region=region,
        )
        generated = generate_iam_policy(
            IamPolicySpec(
                mode=mode,
                function_name=function_name,
                region=region,
                account_id=resolved_account_id,
                include_logs=include_logs,
            )
        )
        policy_json = generated.to_json()
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(policy_json, encoding="utf-8")
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    if json_only:
        typer.echo(policy_json, nl=False)
        return

    typer.echo(render_iam_policy_output(generated), nl=False)
    if output_path is not None:
        typer.echo(f"Policy written to {output_path}")


def _handle_cli_error(exc: LambdaOptError) -> NoReturn:
    if debug_mode:
        traceback_text = traceback.format_exc()
        if traceback_text.strip() != "NoneType: None":
            typer.echo(redact_text(traceback_text), err=True)

    typer.echo(redact_text(f"Error: {exc}"), err=True)
    raise typer.Exit(1)


def _resolve_region(region: str | None) -> str | None:
    return region or cli_config.default_region


def _resolve_profile(profile: str | None) -> str | None:
    return profile or cli_config.default_profile


@app.command(rich_help_panel="Core workflows")
def tune(
    p95: Annotated[float, typer.Option("--p95", min=0.0, help="Target p95 latency in ms.")],
    monthly_requests: Annotated[
        int,
        typer.Option("--monthly-requests", min=0, help="Monthly request count."),
    ] = 1_000_000,
    output_dir: Annotated[
        Path,
        typer.Option("--output", help="Directory where reports will be written."),
    ] = Path("reports/tune"),
    input_path: Annotated[
        Path | None,
        typer.Option(
            "--input",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="JSON benchmark results file.",
        ),
    ] = None,
    candidates_path: Annotated[
        Path | None,
        typer.Option(
            "--candidates",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="JSON mapping of candidate configs to separate test Lambda functions.",
        ),
    ] = None,
    trials: Annotated[
        int,
        typer.Option("--trials", min=1, help="Measured invocations per candidate function."),
    ] = 30,
    warmup: Annotated[
        int,
        typer.Option("--warmup", min=0, help="Warmup invocations before measured trials."),
    ] = 0,
    delay_ms: Annotated[
        int,
        typer.Option("--delay-ms", min=0, help="Delay between invocations in milliseconds."),
    ] = 0,
    payload: Annotated[
        Path,
        typer.Option(
            "--payload",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="JSON payload file for candidate function invocations.",
        ),
    ] = Path("examples/payload.json"),
    dry_run_plan: Annotated[
        bool,
        typer.Option(
            "--dry-run-plan",
            help="Validate and print candidate benchmark plan without invoking functions.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Skip confirmation before invoking candidate functions."),
    ] = False,
    allow_production_candidate: Annotated[
        bool,
        typer.Option(
            "--allow-production-candidate",
            help="Allow candidates that appear to reference $LATEST or production aliases.",
        ),
    ] = False,
    region: Annotated[str | None, typer.Option("--region", help="AWS region.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="AWS profile name.")] = None,
    output_format: Annotated[
        Literal["markdown", "json", "both"],
        typer.Option("--format", help="Output format to write."),
    ] = "both",
) -> None:
    """Run a local SLO-aware optimization workflow from benchmark results."""
    try:
        benchmark_results, extra_warnings = _load_tune_benchmark_results(
            input_path=input_path,
            candidates_path=candidates_path,
            trials=trials,
            warmup=warmup,
            delay_ms=delay_ms,
            payload=payload,
            dry_run_plan=dry_run_plan,
            yes=yes,
            allow_production_candidate=allow_production_candidate,
            region=_resolve_region(region),
            profile=_resolve_profile(profile),
        )
        recommendation = _run_local_optimization_workflow(
            benchmark_results=benchmark_results,
            target_p95_ms=p95,
            monthly_requests=monthly_requests,
            output_dir=output_dir,
            output_format=output_format,
            extra_warnings=extra_warnings,
        )
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    if candidates_path is not None:
        typer.echo("Benchmarked separate candidate test functions; no production config mutated.")
    _print_summary(recommendation, p95, output_dir)


@app.command(rich_help_panel="Start here")
def simulate(
    workload: Annotated[
        WorkloadName,
        typer.Option("--workload", help="Synthetic workload profile to simulate."),
    ],
    p95: Annotated[float, typer.Option("--p95", min=0.0, help="Target p95 latency in ms.")],
    monthly_requests: Annotated[
        int,
        typer.Option("--monthly-requests", min=0, help="Monthly request count."),
    ],
    samples: Annotated[
        int,
        typer.Option("--samples", min=1, help="Latency samples to generate per configuration."),
    ] = DEFAULT_SAMPLE_COUNT,
    seed: Annotated[
        int,
        typer.Option("--seed", help="Deterministic simulator seed."),
    ] = DEFAULT_SEED,
    output_dir: Annotated[
        Path,
        typer.Option("--output", help="Directory where reports will be written."),
    ] = Path("reports/simulated"),
) -> None:
    """Generate synthetic benchmarks and run the local optimizer."""
    try:
        benchmark_results, simulator_warnings = replay_workload(
            workload=workload,
            samples=samples,
            seed=seed,
        )
        recommendation = _run_local_optimization_workflow(
            benchmark_results=benchmark_results,
            target_p95_ms=p95,
            monthly_requests=monthly_requests,
            output_dir=output_dir,
            output_format="both",
            extra_warnings=simulator_warnings,
        )
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    typer.echo(f"Simulated workload: {workload} ({samples} samples/config, seed {seed})")
    _print_summary(recommendation, p95, output_dir)


@app.command(rich_help_panel="Advanced")
def plan(
    function_name: Annotated[str, typer.Argument(help="Lambda function name or ARN.")],
    p95: Annotated[float, typer.Option("--p95", min=0.0, help="Target p95 latency in ms.")],
    region: Annotated[str | None, typer.Option("--region", help="AWS region.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="AWS profile name.")] = None,
) -> None:
    """Create a read-only benchmark plan from live Lambda metadata."""
    try:
        effective_region = _resolve_region(region)
        effective_profile = _resolve_profile(profile)
        client = lambda_client_factory(profile=effective_profile, region=effective_region)
        function_configuration = client.get_function_configuration(function_name)
        benchmark_plan = create_benchmark_plan(
            function_name=function_name,
            current_config=function_configuration.config,
        )
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    _print_benchmark_plan(
        benchmark_plan,
        target_p95_ms=p95,
        region=effective_region,
        profile=effective_profile,
        runtime=function_configuration.metadata.get("runtime"),
    )


@app.command(rich_help_panel="Advanced")
def bench(
    function_name: Annotated[str, typer.Argument(help="Lambda function name or ARN.")],
    trials: Annotated[int, typer.Option("--trials", min=1, help="Measured invocations.")] = 50,
    warmup: Annotated[
        int,
        typer.Option("--warmup", min=0, help="Warmup invocations before measured trials."),
    ] = 0,
    delay_ms: Annotated[
        int,
        typer.Option("--delay-ms", min=0, help="Delay between invocations in milliseconds."),
    ] = 0,
    payload: Annotated[
        Path,
        typer.Option(
            "--payload",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="JSON payload file for synchronous invocation.",
        ),
    ] = Path("examples/payload.json"),
    region: Annotated[str | None, typer.Option("--region", help="AWS region.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="AWS profile name.")] = None,
    p95: Annotated[float, typer.Option("--p95", min=0.0, help="Target p95 latency in ms.")] = 500,
    monthly_requests: Annotated[
        int,
        typer.Option("--monthly-requests", min=0, help="Monthly request count."),
    ] = 1_000_000,
    output_dir: Annotated[
        Path,
        typer.Option("--output", help="Directory where reports will be written."),
    ] = Path("reports/bench-current"),
) -> None:
    """Benchmark the currently deployed Lambda configuration without changing it."""
    try:
        effective_region = _resolve_region(region)
        effective_profile = _resolve_profile(profile)
        client = lambda_client_factory(profile=effective_profile, region=effective_region)
        function_configuration = client.get_function_configuration(function_name)
        benchmark_result = current_config_benchmark_runner(
            client=client._client,
            function_name=function_name,
            config=function_configuration.config,
            payload_path=payload,
            trials=trials,
            warmup=warmup,
            delay_ms=delay_ms,
            runtime=_metadata_string(function_configuration.metadata.get("runtime")),
            region=effective_region,
        )
        recommendation = _run_local_optimization_workflow(
            benchmark_results=[benchmark_result],
            target_p95_ms=p95,
            monthly_requests=monthly_requests,
            output_dir=output_dir,
            output_format="both",
            extra_warnings=[
                CURRENT_CONFIG_ONLY_WARNING,
                CLIENT_OBSERVED_DURATION_WARNING,
                "No production Lambda configuration was changed.",
            ],
        )
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    typer.echo(
        "Benchmarked current deployed config only; no memory or architecture comparison "
        "was performed."
    )
    _print_summary(recommendation, p95, output_dir)


@app.command(rich_help_panel="Core workflows")
def analyze(
    function_name: Annotated[str, typer.Argument(help="Lambda function name or ARN.")],
    window: Annotated[
        str,
        typer.Option("--window", help="Observation window: 1h, 6h, 24h, or 7d."),
    ] = "24h",
    p95: Annotated[float, typer.Option("--p95", min=0.0, help="Target p95 latency in ms.")] = 500,
    region: Annotated[str | None, typer.Option("--region", help="AWS region.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="AWS profile name.")] = None,
    monthly_requests: Annotated[
        int,
        typer.Option("--monthly-requests", min=0, help="Monthly request count."),
    ] = 1_000_000,
    include_logs: Annotated[
        bool,
        typer.Option("--include-logs", help="Analyze Lambda REPORT logs for cold starts."),
    ] = False,
    output_dir: Annotated[
        Path,
        typer.Option("--output", help="Directory where reports will be written."),
    ] = Path("reports/analyze"),
) -> None:
    """Analyze production Lambda CloudWatch metrics without changing anything."""
    try:
        effective_region = _resolve_region(region)
        effective_profile = _resolve_profile(profile)
        analysis = _run_cloudwatch_analysis_workflow(
            function_name=function_name,
            window=window,
            target_p95_ms=p95,
            region=effective_region,
            profile=effective_profile,
            monthly_requests=monthly_requests,
            include_logs=include_logs,
            output_dir=output_dir,
        )
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    typer.echo(f"Analyzed CloudWatch metrics for {function_name} over {window}.")
    typer.echo(f"SLO health: {_cloudwatch_slo_status(analysis.slo_passed)}")
    typer.echo(f"Reports written to {output_dir}")


@app.command(rich_help_panel="Advanced")
def watch(
    function_name: Annotated[str, typer.Argument(help="Lambda function name or ARN.")],
    p95: Annotated[float, typer.Option("--p95", min=0.0, help="Target p95 latency in ms.")],
    window: Annotated[
        str,
        typer.Option("--window", help="Observation window: 1h, 6h, 24h, or 7d."),
    ] = "15m",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Only recommend actions; never mutate infrastructure."),
    ] = True,
    once: Annotated[bool, typer.Option("--once", help="Run one evaluation and exit.")] = True,
    loop: Annotated[bool, typer.Option("--loop", help="Reserved for future daemon mode.")] = False,
    region: Annotated[str | None, typer.Option("--region", help="AWS region.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="AWS profile name.")] = None,
) -> None:
    """Run one dry-run adaptive watch evaluation."""
    if loop or not once:
        _handle_cli_error(LambdaOptSafetyError("Loop mode is not implemented yet. Use --once."))
    if not dry_run:
        _handle_cli_error(
            LambdaOptSafetyError(
                "Only --dry-run mode is supported; no production mutation is allowed."
            )
        )

    try:
        start_time, end_time, period_seconds = parse_window(window)
        effective_region = _resolve_region(region)
        effective_profile = _resolve_profile(profile)
        lambda_client = lambda_client_factory(profile=effective_profile, region=effective_region)
        cloudwatch_client = cloudwatch_client_factory(
            profile=effective_profile,
            region=effective_region,
        )
        function_configuration = lambda_client.get_function_configuration(function_name)
        metrics = cloudwatch_client.fetch_lambda_metrics(
            function_name=function_name,
            start_time=start_time,
            end_time=end_time,
            period_seconds=period_seconds,
        )
        analysis = analyze_cloudwatch_metrics(
            metrics=metrics,
            current_config=function_configuration.config,
            target_p95_ms=p95,
            monthly_requests=0,
            window_label=window,
        )
        decision = evaluate_controller(
            ControllerInput(
                current_config=function_configuration.config,
                observed_p95_ms=analysis.observed_p95_ms,
                observed_p99_ms=analysis.observed_p99_ms,
                target_p95_ms=p95,
                cold_start_rate=0.0,
                error_rate=analysis.error_rate,
                throttle_rate=analysis.throttle_rate,
                current_estimated_cost=analysis.cost_estimate,
            )
        )
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    typer.echo(f"Watch dry-run evaluation for {function_name} over {window}")
    typer.echo(f"Action: {decision.action}")
    typer.echo(f"Reasoning: {decision.reasoning}")
    typer.echo("No production infrastructure was mutated.")


@app.command(rich_help_panel="Advanced")
def dashboard(
    report_dir: Annotated[
        Path,
        typer.Option(
            "--report",
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="LambdaOpt report directory to open.",
        ),
    ],
) -> None:
    """Open the optional Streamlit dashboard for a LambdaOpt report directory."""
    try:
        launch_dashboard(report_dir)
    except LambdaOptError as exc:
        _handle_cli_error(exc)


@app.command(rich_help_panel="Start here")
def doctor(
    function_name: Annotated[
        str | None,
        typer.Argument(help="Optional Lambda function name or ARN to check."),
    ] = None,
    region: Annotated[str | None, typer.Option("--region", help="AWS region.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="AWS profile name.")] = None,
    output_dir: Annotated[
        Path,
        typer.Option("--output", help="Report output directory to verify."),
    ] = Path("reports"),
    include_logs: Annotated[
        bool,
        typer.Option("--include-logs", help="Check CloudWatch Logs permissions."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print structured JSON output."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Enable verbose logging for this command."),
    ] = False,
) -> None:
    """Check local environment and optional AWS readiness without mutation."""
    if verbose:
        configure_logging(verbose=True)
    try:
        result = run_doctor(
            function_name=function_name,
            region=_resolve_region(region),
            profile=_resolve_profile(profile),
            output_dir=output_dir,
            include_logs=include_logs,
        )
    except LambdaOptConfigError as exc:
        typer.echo(redact_text(f"Error: {exc}"), err=True)
        raise typer.Exit(2) from exc
    except LambdaOptError as exc:
        _handle_cli_error(exc)

    if json_output:
        typer.echo(json.dumps(redact_value(result.model_dump(mode="json")), indent=2))
    else:
        typer.echo(render_doctor_text(result))
    raise typer.Exit(result.exit_code)


def _print_benchmark_plan(
    plan: BenchmarkPlan,
    *,
    target_p95_ms: float,
    region: str | None,
    profile: str | None,
    runtime: object,
) -> None:
    current = plan.current_config
    typer.echo(f"Benchmark plan for {plan.function_name}")
    typer.echo(f"Target p95: {target_p95_ms:g} ms")
    typer.echo(f"Region: {region or 'boto3 default'}")
    typer.echo(f"Profile: {profile or 'boto3 default'}")
    typer.echo(
        "Current config: "
        f"{current.memory_mb}MB {current.architecture}, "
        f"timeout {current.timeout_seconds}s, "
        f"provisioned concurrency {current.provisioned_concurrency}"
    )
    if runtime:
        typer.echo(f"Runtime: {runtime}")

    typer.echo("Candidate configs:")
    for candidate in plan.candidate_configs:
        typer.echo(
            "  - "
            f"{candidate.memory_mb}MB {candidate.architecture}, "
            f"timeout {candidate.timeout_seconds}s, "
            f"provisioned concurrency {candidate.provisioned_concurrency}"
        )

    typer.echo("Safety notes:")
    for note in plan.safety_notes:
        typer.echo(f"  - {note}")
    typer.echo(
        "Suggested next command: "
        f"lambdaopt simulate --workload cpu-bound --p95 {target_p95_ms:g} "
        "--monthly-requests 1000000 --output reports/plan-preview"
    )


def _metadata_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _cloudwatch_slo_status(slo_passed: bool | None) -> str:
    if slo_passed is True:
        return "healthy"
    if slo_passed is False:
        return "risky"
    return "unknown"


def _run_start_local_demo(
    *,
    target_p95_ms: float,
    monthly_requests: int,
    output_dir: Path,
) -> Recommendation:
    doctor_result = run_doctor(output_dir=output_dir)
    if doctor_result.overall_status == "fail":
        raise LambdaOptConfigError("Local environment is not ready. Run `lambdaopt doctor`.")

    benchmark_results, simulator_warnings = replay_workload(
        workload="cpu-bound",
        samples=DEFAULT_SAMPLE_COUNT,
        seed=DEFAULT_SEED,
    )
    return _run_local_optimization_workflow(
        benchmark_results=benchmark_results,
        target_p95_ms=target_p95_ms,
        monthly_requests=monthly_requests,
        output_dir=output_dir,
        output_format="both",
        extra_warnings=[
            "Local demo generated from deterministic synthetic benchmark data.",
            *simulator_warnings,
        ],
    )


def _print_start_local_summary(
    recommendation: Recommendation,
    target_p95_ms: float,
    output_dir: Path,
) -> None:
    config = recommendation.recommended_config
    typer.echo("LambdaOpt Start")
    typer.echo("")
    typer.echo("PASS  Local environment ready")
    typer.echo("PASS  Demo optimization completed")
    typer.echo(f"PASS  Report written: {output_dir / 'optimization_report.md'}")
    typer.echo("")
    typer.echo(
        "Recommendation: "
        f"{config.memory_mb}MB {config.architecture} for p95 <= {target_p95_ms:g}ms."
    )
    typer.echo("")
    typer.echo("Next:")
    typer.echo("  Open the report above, or run against a sandbox Lambda:")
    typer.echo("  lambdaopt start my-function --region us-east-1 --p95 500")
    typer.echo("")
    typer.echo("Safety: this local path does not call AWS or mutate infrastructure.")


def _print_start_aws_summary(
    *,
    function_name: str,
    target_p95_ms: float,
    region: str | None,
    output_dir: Path,
    doctor_result: DoctorResult,
    include_logs: bool,
) -> None:
    status_label = {
        "pass": "READY",
        "warn": "READY WITH WARNINGS",
        "fail": "NOT READY",
    }[doctor_result.overall_status]
    typer.echo("LambdaOpt Start")
    typer.echo("")
    typer.echo(f"Readiness: {status_label}")
    for check in _important_start_checks(doctor_result):
        typer.echo(f"{check.status.upper():<5} {check.message}")

    typer.echo("")
    if doctor_result.overall_status == "fail":
        typer.echo("Next:")
        typer.echo("  Fix the failed checks above, or generate a least-privilege policy:")
        typer.echo(
            "  "
            + _iam_generate_command(
                function_name=function_name,
                region=region,
                include_logs=include_logs,
                target_mode="analyze-with-logs" if include_logs else "analyze",
            )
        )
    else:
        typer.echo("Next:")
        typer.echo("  Analyze production metrics without mutation:")
        typer.echo(
            "  "
            + _analyze_command(
                function_name=function_name,
                region=region,
                target_p95_ms=target_p95_ms,
                output_dir=output_dir,
                include_logs=include_logs,
            )
        )
        typer.echo("")
        typer.echo("  Or let start run that analysis now:")
        typer.echo(
            "  "
            + _start_run_analyze_command(
                function_name=function_name,
                region=region,
                target_p95_ms=target_p95_ms,
                include_logs=include_logs,
            )
        )

    typer.echo("")
    typer.echo("Safety: start does not invoke Lambda or mutate AWS unless --run-analyze is used,")
    typer.echo("and --run-analyze reads CloudWatch only.")


def _print_start_analyze_summary(
    *,
    function_name: str,
    window: str,
    output_dir: Path,
    analysis_status: CloudWatchAnalysis,
) -> None:
    typer.echo("LambdaOpt Start")
    typer.echo("")
    typer.echo(f"PASS  CloudWatch analysis completed for {function_name} over {window}")
    typer.echo(f"PASS  Report written: {output_dir / 'optimization_report.md'}")
    typer.echo(f"SLO health: {_cloudwatch_slo_status(analysis_status.slo_passed)}")
    typer.echo("")
    typer.echo("Next:")
    typer.echo(
        "  Review the report and run benchmark workflows only on non-production test targets."
    )
    typer.echo("Safety: no Lambda configuration was changed.")


def _important_start_checks(doctor_result: DoctorResult) -> list[DoctorCheck]:
    important_names = {
        "credentials",
        "caller_identity",
        "region",
        "function",
        "lambda_get_config",
        "metrics",
        "logs",
    }
    return [check for check in doctor_result.checks if check.name in important_names]


def _iam_generate_command(
    *,
    function_name: str,
    region: str | None,
    include_logs: bool,
    target_mode: str,
) -> str:
    command = (
        "lambdaopt iam generate "
        f"--mode {target_mode} "
        f"--function {function_name} "
        f"--region {region or 'us-east-1'} "
        "--account-id ACCOUNT_ID"
    )
    if include_logs and target_mode == "watch-dry-run":
        command += " --include-logs"
    return command


def _analyze_command(
    *,
    function_name: str,
    region: str | None,
    target_p95_ms: float,
    output_dir: Path,
    include_logs: bool,
) -> str:
    command = (
        f"lambdaopt analyze {function_name} --window 24h --p95 {target_p95_ms:g} "
        f"--region {region or 'us-east-1'} --output {output_dir}"
    )
    if include_logs:
        command += " --include-logs"
    return command


def _start_run_analyze_command(
    *,
    function_name: str,
    region: str | None,
    target_p95_ms: float,
    include_logs: bool,
) -> str:
    command = (
        f"lambdaopt start {function_name} --region {region or 'us-east-1'} "
        f"--p95 {target_p95_ms:g} --run-analyze"
    )
    if include_logs:
        command += " --include-logs"
    return command


def _run_cloudwatch_analysis_workflow(
    *,
    function_name: str,
    window: str,
    target_p95_ms: float,
    region: str | None,
    profile: str | None,
    monthly_requests: int,
    include_logs: bool,
    output_dir: Path,
) -> CloudWatchAnalysis:
    start_time, end_time, period_seconds = parse_window(window)
    lambda_client = lambda_client_factory(profile=profile, region=region)
    cloudwatch_client = cloudwatch_client_factory(
        profile=profile,
        region=region,
    )
    function_configuration = lambda_client.get_function_configuration(function_name)
    metrics = cloudwatch_client.fetch_lambda_metrics(
        function_name=function_name,
        start_time=start_time,
        end_time=end_time,
        period_seconds=period_seconds,
    )
    cold_start_analysis = None
    log_warnings: list[str] = []
    if include_logs:
        try:
            logs_client = logs_client_factory(
                profile=profile,
                region=region,
            )
            report_logs = logs_client.fetch_lambda_report_logs(
                function_name=function_name,
                start_time=start_time,
                end_time=end_time,
            )
            cold_start_analysis = analyze_cold_starts_from_messages(
                [log.message for log in report_logs],
                observed_p95_ms=_latest_metric_value(metrics, "duration_p95"),
                observed_p99_ms=_latest_metric_value(metrics, "duration_p99"),
            )
        except LambdaOptError as exc:
            log_warnings.append(f"CloudWatch Logs cold-start analysis was skipped: {exc}")
    analysis = analyze_cloudwatch_metrics(
        metrics=metrics,
        current_config=function_configuration.config,
        target_p95_ms=target_p95_ms,
        monthly_requests=monthly_requests,
        window_label=window,
        cold_start_analysis=cold_start_analysis,
    )
    if log_warnings:
        analysis = analysis.model_copy(update={"warnings": [*analysis.warnings, *log_warnings]})
    output_dir.mkdir(parents=True, exist_ok=True)
    write_cloudwatch_analysis_report(
        analysis=analysis,
        current_config=function_configuration.config,
        target_p95_ms=target_p95_ms,
        monthly_requests=monthly_requests,
        output_dir=output_dir,
    )
    (output_dir / "cloudwatch_analysis.json").write_text(
        json.dumps(
            redact_value(analysis.model_dump(mode="json")),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return analysis


def _latest_metric_value(metrics: LambdaCloudWatchMetrics, metric_id: str) -> float | None:
    series = metrics.series.get(metric_id)
    if series is None or not series.points:
        return None
    return series.points[-1].value


def _load_tune_benchmark_results(
    *,
    input_path: Path | None,
    candidates_path: Path | None,
    trials: int,
    warmup: int,
    delay_ms: int,
    payload: Path,
    dry_run_plan: bool,
    yes: bool,
    allow_production_candidate: bool,
    region: str | None,
    profile: str | None,
) -> tuple[list[BenchmarkResult], list[str]]:
    if input_path is not None and candidates_path is not None:
        raise LambdaOptError("Use either --input or --candidates, not both.")

    if input_path is None and candidates_path is None:
        raise LambdaOptError("Provide either --input benchmark results or --candidates mapping.")

    if input_path is not None:
        return load_benchmark_results(input_path), []

    if candidates_path is None:
        raise LambdaOptError("Candidate mapping path was not provided.")

    mappings = load_candidate_function_mappings(
        candidates_path,
        allow_production_candidate=allow_production_candidate,
    )
    _print_candidate_benchmark_plan(mappings, trials=trials, warmup=warmup, delay_ms=delay_ms)
    if dry_run_plan:
        raise typer.Exit(0)
    if not yes:
        confirmed = typer.confirm(
            "Invoke all candidate functions now? LambdaOpt will not mutate configuration.",
            default=False,
        )
        if not confirmed:
            raise LambdaOptSafetyError("Candidate benchmarking cancelled by user.")

    client = lambda_client_factory(profile=profile, region=region)
    return (
        candidate_function_benchmark_runner(
            client=client._client,
            mappings=mappings,
            payload_path=payload,
            trials=trials,
            warmup=warmup,
            delay_ms=delay_ms,
            region=region,
        ),
        [
            SEPARATE_TEST_FUNCTIONS_SAFETY_NOTE,
            *candidate_validation_warnings(mappings),
            CLIENT_OBSERVED_DURATION_WARNING,
            "No production Lambda memory or architecture configuration was changed.",
        ],
    )


def _print_candidate_benchmark_plan(
    mappings: CandidateMappings,
    *,
    trials: int,
    warmup: int,
    delay_ms: int,
) -> None:
    typer.echo("Candidate benchmark plan")
    if mappings.base_function_name:
        typer.echo(f"Base function: {mappings.base_function_name}")
    if mappings.notes:
        typer.echo(f"Notes: {mappings.notes}")
    typer.echo("Safety: no Lambda memory, architecture, alias, or production config mutation.")
    typer.echo(f"Estimated measured invocations: {len(mappings.candidates) * trials}")
    if warmup:
        typer.echo(f"Estimated warmup invocations: {len(mappings.candidates) * warmup}")
    if delay_ms:
        typer.echo(f"Delay between invocations: {delay_ms} ms")
    typer.echo("Candidates:")
    for candidate in mappings.candidates:
        typer.echo(
            "  - "
            f"{candidate.name}: {candidate.function_ref} "
            f"({candidate.source_type}, {candidate.memory_mb}MB {candidate.architecture}, "
            f"provisioned concurrency {candidate.provisioned_concurrency})"
        )


def _run_local_optimization_workflow(
    *,
    benchmark_results: list[BenchmarkResult],
    target_p95_ms: float,
    monthly_requests: int,
    output_dir: Path,
    output_format: Literal["markdown", "json", "both"],
    extra_warnings: list[str] | None = None,
) -> Recommendation:
    analyzed_configs = _analyze_benchmark_results(
        benchmark_results=benchmark_results,
        target_p95_ms=target_p95_ms,
        monthly_requests=monthly_requests,
    )
    analyzed_configs = mark_pareto_frontier(analyzed_configs)
    recommendation = recommend_cheapest_slo_config(analyzed_configs, target_p95_ms=target_p95_ms)
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_warning = write_cost_vs_p95_chart(analyzed_configs, output_dir)
    report_warnings = [*(extra_warnings or [])]
    if chart_warning:
        report_warnings.append(chart_warning)

    if output_format in {"json", "both"}:
        write_benchmark_results_json(analyzed_configs, output_dir)
        write_recommendation_json(recommendation, output_dir)

    if output_format in {"markdown", "both"}:
        write_markdown_report(
            analyzed_configs=analyzed_configs,
            recommendation=recommendation,
            target_p95_ms=target_p95_ms,
            monthly_requests=monthly_requests,
            output_dir=output_dir,
            warnings=report_warnings,
        )

    for warning in report_warnings:
        typer.echo(f"Warning: {warning}", err=True)

    return recommendation


def _print_summary(
    recommendation: Recommendation,
    target_p95_ms: float,
    output_dir: Path,
) -> None:
    typer.echo(
        "Recommendation: "
        f"{recommendation.recommended_config.memory_mb}MB "
        f"{recommendation.recommended_config.architecture} "
        f"for p95 <= {target_p95_ms:g}ms "
        f"({recommendation.evidence_strength} evidence)."
    )
    typer.echo(f"Reports written to {output_dir}")


def _analyze_benchmark_results(
    *,
    benchmark_results: list[BenchmarkResult],
    target_p95_ms: float,
    monthly_requests: int,
) -> list[AnalyzedConfig]:
    analyzed_configs: list[AnalyzedConfig] = []
    for result in benchmark_results:
        latency = calculate_latency_stats(result.raw_latencies_ms, target_ms=target_p95_ms)
        cost = estimate_lambda_cost(
            memory_mb=result.config.memory_mb,
            avg_duration_ms=latency.mean_ms,
            monthly_requests=monthly_requests,
            architecture=result.config.architecture,
            provisioned_concurrency=result.config.provisioned_concurrency,
            provisioned_concurrency_hours=(
                DEFAULT_MONTHLY_PROVISIONED_CONCURRENCY_HOURS
                if result.config.provisioned_concurrency > 0
                else 0
            ),
            request_cost_per_million_usd=cli_config.cost_rates.request_cost_per_million_usd,
            x86_compute_cost_per_gb_second_usd=(
                cli_config.cost_rates.x86_compute_cost_per_gb_second_usd
            ),
            arm64_compute_cost_per_gb_second_usd=(
                cli_config.cost_rates.arm64_compute_cost_per_gb_second_usd
            ),
            provisioned_concurrency_cost_per_gb_second_usd=(
                cli_config.cost_rates.provisioned_concurrency_cost_per_gb_second_usd
            ),
            provisioned_concurrency_execution_cost_per_gb_second_usd=(
                cli_config.cost_rates.provisioned_concurrency_execution_cost_per_gb_second_usd
            ),
        )
        cold_start_rate = result.cold_starts / latency.sample_count
        analyzed = AnalyzedConfig(
            config=result.config,
            latency=latency,
            cost=cost,
            cold_start_rate=cold_start_rate,
            slo_passed=latency.p95_ms <= target_p95_ms,
            errors=result.errors,
            metadata=result.metadata,
        )
        analyzed_configs.append(
            analyzed.model_copy(
                update={"risk": assess_config_risk(analyzed, target_p95_ms=target_p95_ms)}
            )
        )

    return analyzed_configs


if __name__ == "__main__":
    app()
