"""Logging setup for LambdaOpt CLI commands."""

import logging

from lambdaopt.security import redact_text

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
_ORIGINAL_LOG_RECORD_FACTORY = logging.getLogRecordFactory()
_REDACTING_FACTORY_INSTALLED = False


class RedactingFilter(logging.Filter):
    """Redact sensitive values before log records are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        _redact_log_record(record)
        return True


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure process-wide logging for CLI execution."""
    global _REDACTING_FACTORY_INSTALLED

    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    if quiet:
        level = logging.WARNING

    if not _REDACTING_FACTORY_INSTALLED:
        logging.setLogRecordFactory(_redacting_log_record_factory)
        _REDACTING_FACTORY_INSTALLED = True

    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
    logging.getLogger().addFilter(RedactingFilter())


def get_logger(name: str) -> logging.Logger:
    """Return a project logger."""
    return logging.getLogger(name)


def _redacting_log_record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
    record = _ORIGINAL_LOG_RECORD_FACTORY(*args, **kwargs)
    _redact_log_record(record)
    return record


def _redact_log_record(record: logging.LogRecord) -> None:
    record.msg = redact_text(record.getMessage())
    record.args = ()
