"""Minimal Lambda handler for LambdaOpt smoke tests."""

from typing import Any


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Return a small deterministic response for benchmark smoke tests."""
    workload = str(event.get("workload", "smoke-test"))
    repeat = int(event.get("repeat", 1000))
    checksum = sum(index % 17 for index in range(max(0, min(repeat, 100_000))))

    return {
        "ok": True,
        "workload": workload,
        "checksum": checksum,
    }
