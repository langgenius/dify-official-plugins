import re
import threading
from datetime import date
from urllib.parse import urlparse

import openai
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from .constants import AZURE_OPENAI_API_VERSION

# Minimum Azure OpenAI dated API version that accepts ``stream_options``
# (added together with ``include_usage`` in the 2024-08-01-preview spec).
# Older versions reject the parameter outright, breaking every streamed
# request; see https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle
_MIN_STREAM_OPTIONS_API_VERSION = "2024-08-01-preview"

# Minimum dated API version exposing the Responses API surface
# (``/responses`` first appeared in the 2025-03-01-preview spec).
# Responses-routed models (gpt-5*, codex) cannot work below this.
_MIN_RESPONSES_API_VERSION = "2025-03-01-preview"

# Dated versions are YYYY-MM-DD[-preview]; anything else is unknown and
# must fail closed instead of passing a lexicographic comparison.
_AZURE_API_VERSION_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}(-preview)?")


def _is_valid_azure_version(version: str) -> bool:
    """Full match plus a real calendar date; rejects trailing junk."""
    if not _AZURE_API_VERSION_PATTERN.fullmatch(version):
        return False
    try:
        date.fromisoformat(version[:10])
    except ValueError:
        return False
    return True

_client_cache: dict[tuple, openai.AzureOpenAI | openai.OpenAI] = {}
_client_cache_lock = threading.Lock()


class _CommonAzureOpenAI:
    @staticmethod
    def _is_v1_api_base(api_base: str) -> bool:
        path = urlparse(api_base.strip()).path.rstrip("/")
        return path.endswith("/openai/v1")

    @classmethod
    def _effective_api_version(cls, credentials: dict) -> str:
        return str(credentials.get("openai_api_version") or AZURE_OPENAI_API_VERSION)

    @classmethod
    def _supports_dated_feature(cls, credentials: dict, min_version: str) -> bool:
        """Whether the configured endpoint accepts a feature introduced at ``min_version``.

        Versionless ``/openai/v1`` endpoints always track the latest surface.
        Dated endpoints sort correctly because versions are ``YYYY-MM-DD``-prefixed;
        malformed or unknown version strings fail closed.
        """
        api_base = str(credentials.get("openai_api_base") or "").strip()
        if cls._is_v1_api_base(api_base):
            return True
        version = cls._effective_api_version(credentials)
        if not _is_valid_azure_version(version):
            return False
        # Compare calendar dates: a GA release on the threshold date must
        # satisfy a '-preview' minimum (lexicographic would rank it below).
        return version[:10] >= min_version[:10]

    @classmethod
    def _supports_stream_options(cls, credentials: dict) -> bool:
        return cls._supports_dated_feature(credentials, _MIN_STREAM_OPTIONS_API_VERSION)

    @classmethod
    def _ensure_responses_api_supported(cls, credentials: dict, base_model_name: str) -> None:
        """Fail fast with an actionable message instead of an opaque failure.

        Models routed to the Responses API require the versionless v1 surface
        or a dated version that exposes ``/responses``. With the historical
        default version this combination previously failed deep inside the
        request with an unhelpful error.
        """
        if cls._supports_dated_feature(credentials, _MIN_RESPONSES_API_VERSION):
            return
        raise ValueError(
            f"Base model '{base_model_name}' uses the Azure OpenAI Responses API, "
            f"which requires an '/openai/v1' endpoint or api-version "
            f">= {_MIN_RESPONSES_API_VERSION} (configured: "
            f"'{cls._effective_api_version(credentials)}'). Point API Base URL at "
            "'https://<resource>.openai.azure.com/openai/v1' or select a newer "
            "API Version."
        )

    @staticmethod
    def _normalize_v1_base_url(api_base: str) -> str:
        return api_base.rstrip("/") + "/"

    @classmethod
    def _to_credential_kwargs(cls, credentials: dict) -> dict:
        """
        Convert credentials to Azure OpenAI client kwargs.
        Supports two authentication methods:
        1. API Key authentication (default)
        2. Microsoft Entra ID with Service Principal (user-provided credentials)
        """
        api_base = str(credentials.get("openai_api_base") or "").strip()
        if not api_base:
            raise ValueError("Azure OpenAI API Base URL is required")
        api_version = credentials.get("openai_api_version") or AZURE_OPENAI_API_VERSION
        auth_method = credentials.get("auth_method", "api_key")
        is_v1_api = cls._is_v1_api_base(api_base)

        credentials_kwargs = {
            "timeout": openai.Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }
        if is_v1_api:
            credentials_kwargs["base_url"] = cls._normalize_v1_base_url(api_base)
        else:
            credentials_kwargs["azure_endpoint"] = api_base
            credentials_kwargs["api_version"] = api_version

        if auth_method == "entra_id_service_principal":
            # Use Microsoft Entra ID with Service Principal (user-provided credentials)
            try:
                from azure.identity import (
                    ClientSecretCredential,
                    get_bearer_token_provider,
                )

                client_id = credentials.get("azure_client_id")
                tenant_id = credentials.get("azure_tenant_id")
                client_secret = credentials.get("azure_client_secret")

                if not all([client_id, tenant_id, client_secret]):
                    raise ValueError(
                        "Application (Client) ID, Directory (Tenant) ID, and Client Secret "
                        "are required when using Service Principal authentication"
                    )

                # Create Service Principal credential using user-provided credentials
                # These credentials are from the user's configuration, not from environment
                azure_credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
                if is_v1_api:
                    credentials_kwargs["api_key"] = get_bearer_token_provider(
                        azure_credential,
                        "https://cognitiveservices.azure.com/.default",
                    )
                else:
                    credentials_kwargs["azure_ad_token_provider"] = (
                        lambda: azure_credential.get_token(
                            "https://cognitiveservices.azure.com/.default"
                        ).token
                    )
            except ImportError as e:
                raise ImportError(
                    "azure-identity package is required for Entra ID authentication. "
                    "azure-identity is declared in pyproject.toml; run `uv sync` in the plugin directory."
                ) from e
        else:
            # Use API Key authentication (default)
            api_key = credentials.get("openai_api_key")
            if not api_key:
                raise ValueError(
                    "API Key is required when using API Key authentication method"
                )
            credentials_kwargs["api_key"] = api_key

        return credentials_kwargs

    @staticmethod
    def _credential_cache_key(credentials: dict) -> tuple:
        auth_method = credentials.get("auth_method", "api_key")
        api_base = str(credentials.get("openai_api_base") or "").strip()
        api_version = credentials.get("openai_api_version") or AZURE_OPENAI_API_VERSION
        return (
            api_base,
            auth_method,
            credentials.get("openai_api_key"),
            credentials.get("azure_tenant_id"),
            credentials.get("azure_client_id"),
            credentials.get("azure_client_secret"),
            api_version,
        )

    @classmethod
    def _build_client(cls, credentials: dict):
        client_kwargs = cls._to_credential_kwargs(credentials)
        if cls._is_v1_api_base(str(credentials.get("openai_api_base") or "")):
            return openai.OpenAI(**client_kwargs)
        return openai.AzureOpenAI(**client_kwargs)

    @classmethod
    def _create_client(cls, credentials: dict, *, use_cache: bool = True):
        if not use_cache:
            return cls._build_client(credentials)

        cache_key = cls._credential_cache_key(credentials)
        with _client_cache_lock:
            if cache_key not in _client_cache:
                _client_cache[cache_key] = cls._build_client(credentials)
            return _client_cache[cache_key]

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [openai.APIConnectionError, openai.APITimeoutError],
            InvokeServerUnavailableError: [openai.InternalServerError],
            InvokeRateLimitError: [openai.RateLimitError],
            InvokeAuthorizationError: [
                openai.AuthenticationError,
                openai.PermissionDeniedError,
            ],
            InvokeBadRequestError: [
                openai.BadRequestError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
                openai.APIError,
            ],
        }

    @staticmethod
    def _get_base_model_name(credentials: dict) -> str:
        base_model_name = credentials.get("base_model_name")
        if not base_model_name:
            raise ValueError("Base Model Name is required")
        return base_model_name
