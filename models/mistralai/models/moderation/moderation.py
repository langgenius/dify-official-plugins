import json
from typing import Optional

import requests
from dify_plugin.entities.model import ModelPropertyKey
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.moderation_model import ModerationModel


class MistralAIModerationModel(ModerationModel):
    """
    Model class for MistralAI moderation model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        text: str,
        user: Optional[str] = None,
    ) -> bool:
        """
        Invoke moderation model

        :param model: model name
        :param credentials: model credentials
        :param text: text to moderate
        :param user: unique user id
        :return: false if text is safe, true otherwise
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise CredentialsValidateFailedError("API key is required")

        # chars per chunk
        length = self._get_max_characters_per_chunk(model, credentials)
        text_chunks = [text[i:i + length] for i in range(0, len(text), length)]

        max_text_chunks = self._get_max_chunks(model, credentials)
        chunks = [text_chunks[i:i + max_text_chunks] for i in range(0, len(text_chunks), max_text_chunks)]

        for text_chunk in chunks:
            moderation_result = self._moderation_invoke(model=model, api_key=api_key, texts=text_chunk)

            # Check if any category is flagged as harmful
            for result in moderation_result.get("results", []):
                categories = result.get("categories", {})
                for category, is_flagged in categories.items():
                    if is_flagged:
                        return True

        return False

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise CredentialsValidateFailedError("API key is required")

            # Test with a simple text
            self._moderation_invoke(
                model=model,
                api_key=api_key,
                texts=["test"],
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _moderation_invoke(self, model: str, api_key: str, texts: list[str]) -> dict:
        """
        Invoke moderation model

        :param model: model name
        :param api_key: API key
        :param texts: texts to moderate
        :return: moderation result
        """
        url = "https://api.mistral.ai/v1/moderations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": model,
            "input": texts,
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
        except requests.exceptions.Timeout:
            raise InvokeServerUnavailableError("Request timeout")
        except requests.exceptions.ConnectionError:
            raise InvokeConnectionError("Connection error")

        if response.status_code != 200:
            try:
                error_data = response.json()
                error_message = error_data.get("message", f"HTTP {response.status_code}")
            except:
                error_message = f"HTTP {response.status_code}"

            if response.status_code == 401:
                raise InvokeAuthorizationError(error_message)
            elif response.status_code == 429:
                raise InvokeRateLimitError(error_message)
            elif response.status_code >= 500:
                raise InvokeServerUnavailableError(error_message)
            else:
                raise InvokeBadRequestError(error_message)

        try:
            result = response.json()
        except json.JSONDecodeError:
            raise InvokeServerUnavailableError("Invalid response format")

        return result

    def _get_max_characters_per_chunk(self, model: str, credentials: dict) -> int:
        """
        Get max characters per chunk

        :param model: model name
        :param credentials: model credentials
        :return: max characters per chunk
        """
        model_schema = self.get_model_schema(model, credentials)

        if model_schema and ModelPropertyKey.MAX_CHARACTERS_PER_CHUNK in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.MAX_CHARACTERS_PER_CHUNK]

        # Default for Mistral moderation (8k context ≈ 32k characters)
        return 32000

    def _get_max_chunks(self, model: str, credentials: dict) -> int:
        """
        Get max chunks for given moderation model

        :param model: model name
        :param credentials: model credentials
        :return: max chunks
        """
        model_schema = self.get_model_schema(model, credentials)

        if model_schema and ModelPropertyKey.MAX_CHUNKS in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.MAX_CHUNKS]

        return 1

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [requests.exceptions.ConnectionError, requests.exceptions.Timeout],
            InvokeServerUnavailableError: [requests.exceptions.HTTPError, json.JSONDecodeError],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [requests.exceptions.RequestException, KeyError],
        }
