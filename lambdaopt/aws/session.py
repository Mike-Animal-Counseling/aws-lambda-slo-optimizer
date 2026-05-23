"""AWS session helpers for read-only Lambda metadata access."""

from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError, ProfileNotFound

from lambdaopt.exceptions import AwsCredentialsError, AwsIntegrationError


def create_aws_session(
    *,
    profile: str | None = None,
    region: str | None = None,
) -> boto3.session.Session:
    """Create a boto3 session from optional profile and region values."""
    try:
        session = boto3.Session(profile_name=profile, region_name=region)
    except ProfileNotFound as exc:
        raise AwsCredentialsError(f"AWS profile not found: {profile}") from exc
    except BotoCoreError as exc:
        raise AwsIntegrationError(f"Could not create AWS session: {exc}") from exc

    _validate_session_credentials(session)
    return session


def create_lambda_boto_client(
    *,
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Create a boto3 Lambda client from optional profile and region values."""
    session = create_aws_session(profile=profile, region=region)
    try:
        return session.client("lambda")
    except NoCredentialsError as exc:
        raise AwsCredentialsError(
            "AWS credentials were not found. Configure credentials or pass --profile."
        ) from exc
    except BotoCoreError as exc:
        raise AwsIntegrationError(f"Could not create Lambda client: {exc}") from exc


def create_cloudwatch_boto_client(
    *,
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Create a boto3 CloudWatch client from optional profile and region values."""
    session = create_aws_session(profile=profile, region=region)
    try:
        return session.client("cloudwatch")
    except NoCredentialsError as exc:
        raise AwsCredentialsError(
            "AWS credentials were not found. Configure credentials or pass --profile."
        ) from exc
    except BotoCoreError as exc:
        raise AwsIntegrationError(f"Could not create CloudWatch client: {exc}") from exc


def create_logs_boto_client(
    *,
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Create a boto3 CloudWatch Logs client from optional profile and region values."""
    session = create_aws_session(profile=profile, region=region)
    try:
        return session.client("logs")
    except NoCredentialsError as exc:
        raise AwsCredentialsError(
            "AWS credentials were not found. Configure credentials or pass --profile."
        ) from exc
    except BotoCoreError as exc:
        raise AwsIntegrationError(f"Could not create CloudWatch Logs client: {exc}") from exc


def _validate_session_credentials(session: boto3.session.Session) -> None:
    try:
        credentials = session.get_credentials()
    except NoCredentialsError as exc:
        raise AwsCredentialsError(
            "AWS credentials were not found. Configure credentials or pass --profile."
        ) from exc
    except BotoCoreError as exc:
        raise AwsIntegrationError(f"Could not inspect AWS credentials: {exc}") from exc

    if credentials is None:
        raise AwsCredentialsError(
            "AWS credentials were not found. Configure credentials or pass --profile."
        )
