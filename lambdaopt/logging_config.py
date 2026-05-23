"""Logging setup for LambdaOpt CLI commands."""

import logging

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure process-wide logging for CLI execution."""
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    if quiet:
        level = logging.WARNING

    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)


def get_logger(name: str) -> logging.Logger:
    """Return a project logger."""
    return logging.getLogger(name)
