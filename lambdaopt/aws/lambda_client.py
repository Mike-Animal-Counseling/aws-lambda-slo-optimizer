"""Read-only AWS Lambda client wrapper."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from lambdaopt.aws.session import create_lambda_boto_client
from lambdaopt.exceptions import AwsCredentialsError, AwsIntegrationError, AwsPermissionError
from lambdaopt.models import LambdaConfig


class LambdaBotoClient(Protocol):
    """Subset of boto3 Lambda client methods used by LambdaOpt."""

    def get_function_configuration(self, *, FunctionName: str) -> dict[str, Any]:
        """Return AWS Lambda function configuration metadata."""

    def invoke(
        self,
        *,
        FunctionName: str,
        InvocationType: str,
        Payload: bytes,
    ) -> dict[str, Any]:
        """Synchronously invoke an AWS Lambda function."""


@dataclass(frozen=True)
class LambdaFunctionConfiguration:
    """Parsed Lambda configuration plus AWS metadata."""

    config: LambdaConfig
    metadata: dict[str, Any]


class LambdaClient:
    """Read-only wrapper around AWS Lambda metadata APIs."""

    def __init__(self, boto_client: LambdaBotoClient) -> None:
        self._client = boto_client

    @classmethod
    def from_session_options(
        cls,
        *,
        profile: str | None = None,
        region: str | None = None,
    ) -> "LambdaClient":
        """Create a LambdaClient from optional AWS profile and region."""
        return cls(create_lambda_boto_client(profile=profile, region=region))

    def get_function_configuration(self, function_name: str) -> LambdaFunctionConfiguration:
        """Read a Lambda function's current configuration and metadata."""
        payload = self._get_configuration_payload(function_name)
        return LambdaFunctionConfiguration(
            config=LambdaConfig(
                memory_mb=self.get_function_memory(function_name, payload=payload),
                architecture=self.get_function_architectures(function_name, payload=payload)[0],
                timeout_seconds=self.get_function_timeout(function_name, payload=payload),
                provisioned_concurrency=0,
            ),
            metadata={
                "function_name": payload.get("FunctionName", function_name),
                "function_arn": payload.get("FunctionArn"),
                "runtime": self.get_function_runtime(function_name, payload=payload),
                "handler": payload.get("Handler"),
                "role": payload.get("Role"),
                "last_modified": payload.get("LastModified"),
                "state": payload.get("State"),
                "region": payload.get("Region"),
            },
        )

    def get_function_architectures(
        self,
        function_name: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> list[Literal["x86_64", "arm64"]]:
        """Return configured Lambda instruction set architectures."""
        config = payload or self._get_configuration_payload(function_name)
        raw_architectures = config.get("Architectures") or ["x86_64"]
        architectures = [
            _parse_architecture(architecture)
            for architecture in cast(list[str], raw_architectures)
        ]
        return architectures or ["x86_64"]

    def get_function_runtime(
        self,
        function_name: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> str | None:
        """Return the Lambda runtime string, if present."""
        config = payload or self._get_configuration_payload(function_name)
        runtime = config.get("Runtime")
        return str(runtime) if runtime is not None else None

    def get_function_timeout(
        self,
        function_name: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> int:
        """Return the Lambda timeout in seconds."""
        config = payload or self._get_configuration_payload(function_name)
        return int(config["Timeout"])

    def get_function_memory(
        self,
        function_name: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> int:
        """Return the Lambda memory size in MB."""
        config = payload or self._get_configuration_payload(function_name)
        return int(config["MemorySize"])

    def _get_configuration_payload(self, function_name: str) -> dict[str, Any]:
        try:
            return self._client.get_function_configuration(FunctionName=function_name)
        except NoCredentialsError as exc:
            raise AwsCredentialsError(
                "AWS credentials were not found. Configure credentials or pass --profile."
            ) from exc
        except ClientError as exc:
            raise _client_error_to_lambdaopt_error(exc) from exc
        except BotoCoreError as exc:
            raise AwsIntegrationError(f"Could not read Lambda configuration: {exc}") from exc


def _parse_architecture(value: str) -> Literal["x86_64", "arm64"]:
    if value in {"x86_64", "arm64"}:
        return cast(Literal["x86_64", "arm64"], value)
    raise AwsIntegrationError(f"Unsupported Lambda architecture returned by AWS: {value}")


def _client_error_to_lambdaopt_error(exc: ClientError) -> AwsIntegrationError:
    error = exc.response.get("Error", {})
    code = error.get("Code", "Unknown")
    message = error.get("Message", str(exc))

    if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
        return AwsPermissionError(f"AWS denied read access to Lambda configuration: {message}")

    if code in {"UnrecognizedClientException", "InvalidClientTokenId", "ExpiredTokenException"}:
        return AwsCredentialsError(f"AWS credentials are invalid or expired: {message}")

    return AwsIntegrationError(f"AWS Lambda metadata request failed ({code}): {message}")
