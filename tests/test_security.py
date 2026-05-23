from lambdaopt.security import REDACTED_VALUE, payload_summary, redact_payload


def test_redact_payload_redacts_sensitive_keys_recursively() -> None:
    payload = {
        "username": "user@example.com",
        "password": "super-secret",
        "nested": {
            "api_key": "abc123",
            "items": [{"authorization": "Bearer token"}, {"safe": "value"}],
        },
    }

    redacted = redact_payload(payload)

    assert redacted["username"] == "user@example.com"
    assert redacted["password"] == REDACTED_VALUE
    assert redacted["nested"]["api_key"] == REDACTED_VALUE
    assert redacted["nested"]["items"][0]["authorization"] == REDACTED_VALUE
    assert redacted["nested"]["items"][1]["safe"] == "value"


def test_payload_summary_does_not_include_raw_bytes() -> None:
    summary = payload_summary(b'{"token":"secret-value"}')

    assert summary == {"type": "bytes", "size_bytes": 24}
    assert "secret-value" not in str(summary)


def test_payload_summary_redacts_object_values() -> None:
    summary = payload_summary({"token": "secret-value", "request_id": "abc"})

    assert summary["redacted"] == {"token": REDACTED_VALUE, "request_id": "abc"}
    assert "secret-value" not in str(summary)
