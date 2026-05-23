"""Security helpers for safely handling user payloads and metadata."""

from collections.abc import Mapping, Sequence
from typing import Any

REDACTED_VALUE = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "password",
    "token",
    "secret",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "session_token",
)


def is_sensitive_key(key: str) -> bool:
    """Return true when a key name commonly carries credentials or secrets."""
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_payload(payload: Any) -> Any:
    """Recursively redact sensitive values while preserving payload shape."""
    if isinstance(payload, Mapping):
        return {
            key: REDACTED_VALUE if is_sensitive_key(str(key)) else redact_payload(value)
            for key, value in payload.items()
        }

    if isinstance(payload, tuple):
        return tuple(redact_payload(item) for item in payload)

    if isinstance(payload, Sequence) and not isinstance(payload, str | bytes | bytearray):
        return [redact_payload(item) for item in payload]

    return payload


def payload_summary(payload: Any) -> dict[str, Any]:
    """Return a redacted, bounded summary suitable for logs and reports."""
    if isinstance(payload, bytes | bytearray):
        return {"type": "bytes", "size_bytes": len(payload)}

    if isinstance(payload, str):
        return {"type": "string", "size_chars": len(payload)}

    if isinstance(payload, Mapping):
        return {
            "type": "object",
            "keys": [str(key) for key in payload],
            "redacted": redact_payload(payload),
        }

    if isinstance(payload, Sequence):
        return {"type": "array", "items": len(payload), "redacted": redact_payload(payload)}

    return {"type": type(payload).__name__, "redacted": redact_payload(payload)}
