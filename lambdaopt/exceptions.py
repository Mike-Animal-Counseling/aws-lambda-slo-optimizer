"""Custom exceptions for LambdaOpt."""


class LambdaOptError(Exception):
    """Base exception for all LambdaOpt errors."""


class LambdaOptValidationError(LambdaOptError, ValueError):
    """Raised when optimizer input data fails domain validation."""


class LambdaOptAwsError(LambdaOptError):
    """Raised when AWS integration fails."""


class LambdaOptPermissionError(LambdaOptAwsError, PermissionError):
    """Raised when AWS or local permissions block an operation."""


class LambdaOptConfigError(LambdaOptError):
    """Raised when user configuration is invalid."""


class LambdaOptSafetyError(LambdaOptError):
    """Raised when a requested action violates LambdaOpt safety guardrails."""


class ConfigurationError(LambdaOptConfigError):
    """Backward-compatible alias for configuration errors."""


class DataLoadError(LambdaOptConfigError):
    """Raised when local benchmark data cannot be loaded or parsed."""


class AwsIntegrationError(LambdaOptAwsError):
    """Raised when read-only AWS integration fails."""


class AwsCredentialsError(AwsIntegrationError):
    """Raised when AWS credentials or profile configuration are missing or invalid."""


class AwsPermissionError(LambdaOptPermissionError, AwsIntegrationError):
    """Raised when AWS denies a read-only operation."""


class AwsTimeoutError(AwsIntegrationError):
    """Raised when AWS invocation benchmarking times out or exhausts retries."""
