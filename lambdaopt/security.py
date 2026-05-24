"""Security helpers for safely handling payloads, reports, and logs."""

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REDACTED_VALUE = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "access_key",
    "secret_key",
    "session_token",
    "authorization",
    "api_key",
    "x_api_key",
    "credential",
    "private_key",
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
)
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)\b[^\s\"'`=,:;{}()\[\]]*"
    r"(?:password|passwd|pwd|token|secret|access[-_]?key|secret[-_]?key|"
    r"session[-_]?token|authorization|api[-_]?key|x[-_]?api[-_]?key|"
    r"credential|private[-_]?key|aws[-_]?access[-_]?key[-_]?id|"
    r"aws[-_]?secret[-_]?access[-_]?key|aws[-_]?session[-_]?token)"
    r"[^\s\"'`=,:;{}()\[\]]*\b"
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|token|secret|access[-_]?key|secret[-_]?key|"
    r"session[-_]?token|authorization|api[-_]?key|x[-_]?api[-_]?key|"
    r"credential|private[-_]?key|aws[-_]?access[-_]?key[-_]?id|"
    r"aws[-_]?secret[-_]?access[-_]?key|aws[-_]?session[-_]?token)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def is_sensitive_key(key: str) -> bool:
    """Return true when a key name commonly carries credentials or secrets."""
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_value(value: Any) -> Any:
    """Recursively redact sensitive data from arbitrary JSON-like values."""
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Redact sensitive values from a mapping, including nested structures."""
    return {
        str(key): REDACTED_VALUE if is_sensitive_key(str(key)) else redact_value(value)
        for key, value in data.items()
    }


def redact_text(text: str) -> str:
    """Redact sensitive words and assignment values from free-form text."""
    redacted = SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED_VALUE}",
        text,
    )
    return SENSITIVE_TEXT_PATTERN.sub(REDACTED_VALUE, redacted)


def payload_metadata(path: Path) -> dict[str, Any]:
    """Return safe metadata for a payload file without exposing contents."""
    payload_bytes = path.read_bytes()
    return {
        "path": str(path),
        "size_bytes": len(payload_bytes),
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }


def redact_payload(payload: Any) -> Any:
    """Backward-compatible alias for recursive redaction."""
    return redact_value(payload)


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
            "redacted": redact_mapping(payload),
        }

    if isinstance(payload, Sequence):
        return {"type": "array", "items": len(payload), "redacted": redact_value(payload)}

    return {"type": type(payload).__name__, "redacted": redact_value(payload)}
