import re
from typing import Any
from urllib.parse import urlparse

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class AzureOpenAIProvider(ToolProvider):
    @staticmethod
    def _validate_endpoint(endpoint: str) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ToolProviderCredentialValidationError(
                "Azure OpenAI endpoint must be a valid HTTPS URL."
            )

        if not parsed.netloc.endswith(".openai.azure.com"):
            raise ToolProviderCredentialValidationError(
                "Azure OpenAI endpoint must use an *.openai.azure.com host."
            )

    @staticmethod
    def _validate_api_version(api_version: str) -> None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-preview)?", api_version):
            raise ToolProviderCredentialValidationError(
                "Azure OpenAI API version must look like 2025-04-01-preview."
            )

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            api_key = credentials["azure_openai_api_key"]
            deployment_name = credentials["azure_openai_api_model_name"]
            endpoint = credentials["azure_openai_base_url"]
            api_version = credentials["azure_openai_api_version"]

            if not isinstance(api_key, str) or not api_key.strip():
                raise ToolProviderCredentialValidationError("Azure OpenAI API key is required.")

            if not isinstance(deployment_name, str) or not deployment_name.strip():
                raise ToolProviderCredentialValidationError(
                    "Azure OpenAI deployment name is required."
                )

            if not isinstance(endpoint, str) or not endpoint.strip():
                raise ToolProviderCredentialValidationError("Azure OpenAI endpoint is required.")

            if not isinstance(api_version, str) or not api_version.strip():
                raise ToolProviderCredentialValidationError(
                    "Azure OpenAI API version is required."
                )

            self._validate_endpoint(endpoint)
            self._validate_api_version(api_version)
        except ToolProviderCredentialValidationError:
            raise
        except Exception:
            raise ToolProviderCredentialValidationError(
                "Failed to validate Azure OpenAI configuration. Check the endpoint, deployment name, API version, and API key."
            )
