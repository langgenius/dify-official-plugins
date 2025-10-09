from typing import Any
import openai
from yarl import URL
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider


class PodcastGeneratorProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("api_key")
        base_url = credentials.get("openai_base_url")
        tts_service = credentials.get("tts_service")
        model = credentials.get("model")
        if not api_key:
            raise ToolProviderCredentialValidationError("API key is missing")
        if not tts_service:
            raise ToolProviderCredentialValidationError("TTS service is not specified")
        if tts_service == "openai":
            if base_url:
                base_url = str(URL(base_url) / "v1")
            self._validate_openai_credentials(api_key, base_url)
        elif tts_service == "azure_openai":
            if not base_url:
                raise ToolProviderCredentialValidationError("API Base URL is required for Azure OpenAI")
            if not model:
                raise ToolProviderCredentialValidationError("Model is required for Azure OpenAI")
            self._validate_azure_openai_credentials(api_key, base_url, model)
        else:
            raise ToolProviderCredentialValidationError(f"Unsupported TTS service: {tts_service}")

    def _validate_openai_credentials(self, api_key: str, base_url: str | None) -> None:
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        try:
            client.models.list()
        except openai.AuthenticationError:
            raise ToolProviderCredentialValidationError("Invalid OpenAI API key")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Error validating OpenAI API key: {str(e)}")

    def _validate_azure_openai_credentials(self, api_key: str, base_url: str, model: str) -> None:
        client = openai.AzureOpenAI(api_key=api_key, api_version="2025-04-01-preview", azure_endpoint=base_url)
        try:
            client.audio.speech.create(
                model=model,
                input="Hello Dify!",
                voice="alloy",
            )
        except openai.AuthenticationError:
            raise ToolProviderCredentialValidationError("Invalid Azure OpenAI API key")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Error validating Azure OpenAI API key: {str(e)}")
