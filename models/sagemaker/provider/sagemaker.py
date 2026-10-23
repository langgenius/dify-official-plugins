import functools
import logging
import re
import time
import uuid
from collections.abc import Mapping
from typing import IO, Any

import boto3
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session

from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)

#: Default ``RoleSessionName`` prefix for ``sts:AssumeRole`` calls made by
#: :func:`get_sagemaker_client`. Callers that know their model type pass a more
#: specific prefix (``dify-sagemaker-embedding``, ``dify-sagemaker-rerank``) so
#: the assumed session stays attributable in the target account's CloudTrail.
DEFAULT_ROLE_SESSION_PREFIX = "dify-sagemaker"

#: Lifetime requested for assumed-role credentials. botocore's
#: ``RefreshableCredentials`` re-assumes the role automatically before expiry.
ASSUME_ROLE_DURATION_SECONDS = 3600

# STS constraint on RoleSessionName: 2-64 characters drawn from [\w+=,.@-].
_ROLE_SESSION_NAME_MAX_LEN = 64
_ROLE_SESSION_NAME_INVALID_CHARS = re.compile(r"[^\w+=,.@-]", re.ASCII)


def _build_role_session_name(prefix: str) -> str:
    """Return ``"{prefix}-{unix_ts}"`` sanitised to the STS RoleSessionName rules.

    Characters outside ``[\\w+=,.@-]`` are replaced with ``-`` and the prefix is
    truncated so the whole name fits in 64 characters. The timestamp suffix is
    always present, so the 2-character minimum is satisfied.
    """
    suffix = f"-{int(time.time())}"
    prefix = _ROLE_SESSION_NAME_INVALID_CHARS.sub(
        "-", prefix or DEFAULT_ROLE_SESSION_PREFIX
    )
    return prefix[: _ROLE_SESSION_NAME_MAX_LEN - len(suffix)] + suffix


def _refresh_assume_role_credentials(
    access_key: str | None,
    secret_key: str | None,
    region: str | None,
    role_arn: str,
    role_session_prefix: str,
) -> dict[str, str]:
    """Call ``sts:AssumeRole`` and return ``RefreshableCredentials`` metadata.

    Every input is an explicit parameter and nothing is read from module,
    global or instance state. :func:`get_sagemaker_client` binds an immutable
    snapshot of the *source account* identity with :func:`functools.partial`,
    so the first AssumeRole and every automatic refresh performed later by
    botocore re-assume the role with exactly the same identity: the explicit
    access key / secret key when both are configured, otherwise the runtime
    environment's default credential chain.

    :return: mapping with ``access_key``, ``secret_key``, ``token`` and
        ``expiry_time`` (ISO-8601), the shape
        ``RefreshableCredentials.create_from_metadata`` expects.
    """
    session_kwargs: dict[str, str] = {}
    if region:
        session_kwargs["region_name"] = region
    if access_key and secret_key:
        session_kwargs["aws_access_key_id"] = access_key
        session_kwargs["aws_secret_access_key"] = secret_key
    sts_client = boto3.Session(**session_kwargs).client("sts")

    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=_build_role_session_name(role_session_prefix),
        DurationSeconds=ASSUME_ROLE_DURATION_SECONDS,
    )
    assumed = response["Credentials"]
    return {
        "access_key": assumed["AccessKeyId"],
        "secret_key": assumed["SecretAccessKey"],
        "token": assumed["SessionToken"],
        "expiry_time": assumed["Expiration"].isoformat(),
    }


def get_sagemaker_client(
    service_name: str,
    credentials: Mapping[str, str],
    role_session_prefix: str = DEFAULT_ROLE_SESSION_PREFIX,
) -> Any:
    """Build a fresh boto3 client for a SageMaker-related service.

    Each call constructs a new ``boto3.Session`` so disk-refreshed
    credentials (``aws sso login``, ``saml2aws login``, refreshed IMDS
    role) are picked up on every invocation. boto3's default session
    resolves credentials once per process and reuses them, which would
    otherwise keep a stale ``ExpiredTokenException`` in flight until the
    plugin process restarts.

    Mirrors the shape of ``models/bedrock/provider/get_bedrock_client.py``
    (PR #3535) and the ``tools/aws`` boto3 fix (PR #3545).

    Cross-account access: when ``assume_role_arn`` is configured, the
    source-account session described above is only used to call
    ``sts:AssumeRole``; the returned client signs with the assumed role's
    temporary credentials, which botocore refreshes automatically
    (``RefreshableCredentials``, ``DurationSeconds=3600``). Every refresh
    re-assumes the role with the same explicit source identity that was
    configured when the client was built, never with state that may have
    changed since. When ``assume_role_arn`` is absent or blank the function
    behaves exactly as before and makes no STS call.

    There is deliberately no client cache and no lock here: a fresh session
    per call means there is no shared mutable state that could pair one
    tenant's credentials with another tenant's endpoint, and a slow or failing
    AssumeRole for one caller never blocks another.

    :param service_name: the AWS service name (e.g. ``"sagemaker-runtime"``,
        ``"s3"``, ``"comprehend"``).
    :param credentials: provider credentials mapping. Recognised keys are
        ``aws_access_key_id``, ``aws_secret_access_key``, ``aws_region`` and
        ``assume_role_arn``.
    :param role_session_prefix: prefix of the STS ``RoleSessionName`` used when
        assuming a role; keep it descriptive for CloudTrail auditing. Ignored
        when no role is assumed.
    :return: a fresh boto3 client.
    """
    aws_region = credentials.get("aws_region")
    access_key = credentials.get("aws_access_key_id")
    secret_key = credentials.get("aws_secret_access_key")
    assume_role_arn = (credentials.get("assume_role_arn") or "").strip()

    if assume_role_arn:
        return _get_assumed_role_client(
            service_name,
            access_key=access_key,
            secret_key=secret_key,
            region=aws_region,
            role_arn=assume_role_arn,
            role_session_prefix=role_session_prefix,
        )

    if access_key and secret_key:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=aws_region,
        )
    else:
        session = boto3.Session(region_name=aws_region)
    return session.client(service_name)


def _get_assumed_role_client(
    service_name: str,
    *,
    access_key: str | None,
    secret_key: str | None,
    region: str | None,
    role_arn: str,
    role_session_prefix: str,
) -> Any:
    """Build a client that signs with auto-refreshing assumed-role credentials."""
    # Immutable snapshot of this call's source identity. Bound once here and
    # reused by botocore for every automatic refresh, so a refresh can never
    # pick up credentials belonging to a different configuration or tenant.
    refresh_using = functools.partial(
        _refresh_assume_role_credentials,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        role_arn=role_arn,
        role_session_prefix=role_session_prefix,
    )
    logger.debug(
        "Assuming role %s for %s client (session prefix %s)",
        role_arn,
        service_name,
        role_session_prefix,
    )
    session_credentials = RefreshableCredentials.create_from_metadata(
        metadata=refresh_using(),
        refresh_using=refresh_using,
        method="sts-assume-role",
    )

    botocore_session = get_session()
    botocore_session._credentials = session_credentials
    session = boto3.Session(botocore_session=botocore_session, region_name=region)
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
