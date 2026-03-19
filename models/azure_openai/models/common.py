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
from httpx import Timeout

from .constants import AZURE_OPENAI_API_VERSION


class _CommonAzureOpenAI:
    @staticmethod
    def _is_v1_api_base(api_base: str) -> bool:
        path = urlparse(api_base.strip()).path.rstrip("/")
        return path.endswith("/openai/v1")

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
        api_base = credentials["openai_api_base"].strip()
        api_version = credentials.get("openai_api_version") or AZURE_OPENAI_API_VERSION
        auth_method = credentials.get("auth_method", "api_key")
        is_v1_api = cls._is_v1_api_base(api_base)

        credentials_kwargs = {
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
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
                    "Please install it with: pip install azure-identity"
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

    @classmethod
    def _create_client(cls, credentials: dict):
        client_kwargs = cls._to_credential_kwargs(credentials)
        if cls._is_v1_api_base(credentials["openai_api_base"]):
            return openai.OpenAI(**client_kwargs)
        return openai.AzureOpenAI(**client_kwargs)

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
