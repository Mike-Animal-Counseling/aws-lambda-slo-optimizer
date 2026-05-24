import logging

from pytest import CaptureFixture

from lambdaopt.logging_config import configure_logging
from lambdaopt.security import REDACTED_VALUE, redact_mapping, redact_text

FAKE_ACCESS_KEY = "FAKE_AWS_ACCESS_KEY_ID_FOR_TESTING"
FAKE_SECRET_KEY = "FAKE_AWS_SECRET_ACCESS_KEY_FOR_TESTING"


def test_redact_mapping_redacts_nested_secrets() -> None:
    redacted = redact_mapping(
        {
            "username": "safe-user",
            "password": "do-not-show",
            "nested": {
                "aws_secret_access_key": FAKE_SECRET_KEY,
                "headers": {"x-api-key": "fake-api-key"},
            },
            "items": [{"session_token": "fake-session-token"}],
        }
    )

    assert redacted["username"] == "safe-user"
    assert redacted["password"] == REDACTED_VALUE
    assert redacted["nested"]["aws_secret_access_key"] == REDACTED_VALUE
    assert redacted["nested"]["headers"]["x-api-key"] == REDACTED_VALUE
    assert redacted["items"][0]["session_token"] == REDACTED_VALUE


def test_redact_text_redacts_fake_aws_keys_and_tokens() -> None:
    text = (
        f"aws_access_key_id={FAKE_ACCESS_KEY} "
        f"aws_secret_access_key={FAKE_SECRET_KEY} token=fake-token"
    )

    redacted = redact_text(text)

    assert FAKE_ACCESS_KEY not in redacted
    assert FAKE_SECRET_KEY not in redacted
    assert "fake-token" not in redacted
    assert REDACTED_VALUE in redacted


def test_logging_filter_redacts_sensitive_values(capsys: CaptureFixture[str]) -> None:
    configure_logging(verbose=True)
    logger = logging.getLogger("lambdaopt.test")

    logger.info("token=%s", "fake-token")
    captured = capsys.readouterr()

    assert "fake-token" not in captured.err
    assert REDACTED_VALUE in captured.err
