from collections.abc import Mapping
from typing import Any

import os
import hashlib
import boto3
from botocore.config import Config

from dify_plugin.errors.model import InvokeBadRequestError


# Module-level client cache: maps a cache key to a boto3 client.
# Invalidated on expired token errors via invalidate_client_cache().
_client_cache: dict[str, Any] = {}


def _build_cache_key(service_name: str, credentials: Mapping[str, str]) -> str:
    """Build a deterministic cache key from service name and credential inputs."""
    parts = [
        service_name,
        credentials.get("aws_region", ""),
        credentials.get("auth_method", ""),
        credentials.get("aws_access_key_id", ""),
        credentials.get("bedrock_endpoint_url", ""),
        credentials.get("bedrock_proxy_url", ""),
    ]
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


def invalidate_client_cache() -> None:
    """Clear the cached boto3 clients, forcing fresh credentials on next call."""
    _client_cache.clear()


def get_bedrock_client(service_name: str, credentials: Mapping[str, str]):
    """
    Get or create a boto3 client for Bedrock.

    Clients are cached per (service, credentials) combination. On expired token
    errors, call invalidate_client_cache() before retrying to force a fresh
    client with re-read credentials from disk.
    """
    cache_key = _build_cache_key(service_name, credentials)

    if cache_key in _client_cache:
        return _client_cache[cache_key]

    client = _create_bedrock_client(service_name, credentials)
    _client_cache[cache_key] = client
    return client


def _create_bedrock_client(service_name: str, credentials: Mapping[str, str]):
    """Create a new boto3 client (not cached — called by get_bedrock_client)."""
    region_name = credentials.get("aws_region")
    if not region_name:
        raise InvokeBadRequestError("aws_region is required")

    # Get endpoint URL and proxy URL
    bedrock_endpoint_url = credentials.get("bedrock_endpoint_url")
    bedrock_proxy_url = credentials.get("bedrock_proxy_url")

    # Check if both endpoint URL and proxy URL are provided
    if bedrock_endpoint_url and bedrock_proxy_url:
        raise InvokeBadRequestError("Cannot use both bedrock_endpoint_url and bedrock_proxy_url at the same time. Please choose one or none.")

    # Initialize client config with region
    client_config = Config(region_name=region_name)

    # Configure proxy if provided
    if bedrock_proxy_url:
        client_config.proxies = {
            'http': 'http://' + bedrock_proxy_url,
            'https': 'http://' + bedrock_proxy_url
        }

    # Initialize client parameters
    client_kwargs = {
        'service_name': service_name,
        'config': client_config
    }

    # Add endpoint URL if provided
    if bedrock_endpoint_url and service_name == 'bedrock-runtime':
        client_kwargs['endpoint_url'] = bedrock_endpoint_url

    # Check authentication method
    auth_method = credentials.get("auth_method", "Access_Secret_Key")

    if auth_method == "API_Key":
        # Use API Key authentication
        bedrock_api_key = credentials.get("bedrock_api_key")
        if not bedrock_api_key:
            raise InvokeBadRequestError("bedrock_api_key is required when using API Key authentication")
        
        # Add API Key to client config
        os.environ['AWS_BEARER_TOKEN_BEDROCK'] = bedrock_api_key

    elif auth_method == "Access_Secret_Key":
        # Use IAM authentication (default)
        if 'AWS_BEARER_TOKEN_BEDROCK' in os.environ:
            os.environ.pop('AWS_BEARER_TOKEN_BEDROCK')
        aws_access_key_id = credentials.get("aws_access_key_id")
        aws_secret_access_key = credentials.get("aws_secret_access_key")
        aws_session_token = credentials.get("aws_session_token")
        
        # Add credentials if provided
        if aws_access_key_id and aws_secret_access_key:
            client_kwargs['aws_access_key_id'] = aws_access_key_id
            client_kwargs['aws_secret_access_key'] = aws_secret_access_key
            if aws_session_token:
                client_kwargs['aws_session_token'] = aws_session_token
    else:  # auth_method == "IAM_Role"
        if 'AWS_BEARER_TOKEN_BEDROCK' in os.environ:
            os.environ.pop('AWS_BEARER_TOKEN_BEDROCK')
        # Create a fresh boto3 session to read the latest credentials from disk.
        # This ensures rotated tokens (saml2aws, aws sso) are picked up after
        # cache invalidation.
        session = boto3.Session()
        creds = session.get_credentials()
        if creds:
            frozen = creds.get_frozen_credentials()
            client_kwargs['aws_access_key_id'] = frozen.access_key
            client_kwargs['aws_secret_access_key'] = frozen.secret_key
            if frozen.token:
                client_kwargs['aws_session_token'] = frozen.token

    client = boto3.client(**client_kwargs)
    return client


def is_expired_token_error(exc: Exception) -> bool:
    """Check if an exception indicates expired AWS credentials."""
    msg = str(exc).lower()
    return any(s in msg for s in ("expiredtoken", "expired", "security token", "the security token included in the request is expired"))
