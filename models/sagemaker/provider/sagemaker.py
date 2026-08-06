import logging
import uuid
from collections.abc import Mapping
from typing import IO, Any

import boto3

from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


def get_sagemaker_client(service_name: str, credentials: Mapping[str, str]) -> Any:
    """Build a fresh boto3 client for a SageMaker-related service.

    Each call constructs a new ``boto3.Session`` so disk-refreshed
    credentials (``aws sso login``, ``saml2aws login``, refreshed IMDS
    role) are picked up on every invocation. boto3's default session
    resolves credentials once per process and reuses them, which would
    otherwise keep a stale ``ExpiredTokenException`` in flight until the
    plugin process restarts.

    Mirrors the shape of ``models/bedrock/provider/get_bedrock_client.py``
    (PR #3535) and the ``tools/aws`` boto3 fix (PR #3545).

    :param service_name: the AWS service name (e.g. ``"sagemaker-runtime"``,
        ``"s3"``, ``"comprehend"``).
    :param credentials: provider credentials mapping. Recognised keys are
        ``aws_access_key_id``, ``aws_secret_access_key``, and ``aws_region``.
    :return: a fresh boto3 client.
    """
    aws_region = credentials.get("aws_region")
    access_key = credentials.get("aws_access_key_id")
    secret_key = credentials.get("aws_secret_access_key")

    if access_key and secret_key:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=aws_region,
        )
    else:
        session = boto3.Session(region_name=aws_region)
    return session.client(service_name)


class SageMakerProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials

        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        pass


def buffer_to_s3(s3_client: Any, file: IO[bytes], bucket: str, s3_prefix: str) -> str:
    """
    return s3_uri of this file
    """
    s3_key = f"{s3_prefix}{uuid.uuid4()}.mp3"
    s3_client.put_object(
        Body=file.read(), Bucket=bucket, Key=s3_key, ContentType="audio/mp3"
    )
    return s3_key


def generate_presigned_url(
    s3_client: Any, file: IO[bytes], bucket_name: str, s3_prefix: str, expiration=600
):
    object_key = buffer_to_s3(s3_client, file, bucket_name, s3_prefix)
    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_key},
            ExpiresIn=expiration,
        )
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return None
    return response
