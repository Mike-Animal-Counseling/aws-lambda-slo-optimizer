"""Convert invocation samples into LambdaOpt benchmark results."""

from lambdaopt.benchmark.invoker import InvocationSample
from lambdaopt.models import BenchmarkResult, LambdaConfig

CLIENT_OBSERVED_DURATION_WARNING = (
    "Client-observed latency includes network and SDK overhead and is not the same as "
    "AWS Lambda billed duration."
)


def collect_benchmark_result(
    *,
    function_name: str,
    config: LambdaConfig,
    samples: list[InvocationSample],
    runtime: str | None,
    region: str | None,
) -> BenchmarkResult:
    """Build a BenchmarkResult from raw Lambda invocation samples."""
    return BenchmarkResult(
        config=config,
        raw_latencies_ms=[sample.latency_ms for sample in samples],
        cold_starts=0,
        errors=sum(1 for sample in samples if not sample.succeeded),
        metadata={
            "function_name": function_name,
            "runtime": runtime,
            "region": region,
            "measured_by": "client_observed_latency",
            "warning": CLIENT_OBSERVED_DURATION_WARNING,
            "trials": len(samples),
            "status_codes": [sample.status_code for sample in samples],
            "function_errors": [
                sample.function_error for sample in samples if sample.function_error is not None
            ],
            "payload_response_size_bytes": [
                sample.payload_response_size_bytes for sample in samples
            ],
        },
    )
