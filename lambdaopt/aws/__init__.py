"""Read-only AWS integration package."""

from lambdaopt.aws.cloudwatch_client import CloudWatchClient
from lambdaopt.aws.lambda_client import LambdaClient, LambdaFunctionConfiguration
from lambdaopt.aws.logs_client import LogsClient
from lambdaopt.aws.session import (
    create_aws_session,
    create_cloudwatch_boto_client,
    create_lambda_boto_client,
)

__all__ = [
    "CloudWatchClient",
    "LambdaClient",
    "LambdaFunctionConfiguration",
    "LogsClient",
    "create_aws_session",
    "create_cloudwatch_boto_client",
    "create_lambda_boto_client",
]
