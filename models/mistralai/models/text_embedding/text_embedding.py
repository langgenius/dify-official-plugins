import json
import time
from decimal import Decimal
from typing import Optional

import requests
from dify_plugin.entities.model import EmbeddingInputType, ModelType, PriceType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, TextEmbeddingResult
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.text_embedding_model import TextEmbeddingModel


class MistralAITextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for MistralAI text embedding model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke text embedding model

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise CredentialsValidateFailedError("API key is required")

        url = "https://api.mistral.ai/v1/embeddings"
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

        embeddings = []
        for item in result.get("data", []):
            embeddings.append(item.get("embedding", []))

        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens)

        usage_obj = self._calc_response_usage(
            model=model,
            credentials=credentials,
            tokens=prompt_tokens,
            total_tokens=total_tokens,
        )

        return TextEmbeddingResult(
            embeddings=embeddings,
            usage=usage_obj,
            model=model,
        )

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        """
        Get number of tokens for given texts

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to tokenize
        :return: list of token counts for each text
        """
        # Approximation: 1 token ≈ 4 characters for most languages
        return [len(text) // 4 for text in texts]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :raises: CredentialsValidateFailedError
        """
        try:
            # Test with a simple text
            self._invoke(model, credentials, ["test"])
        except Exception as e:
            raise CredentialsValidateFailedError(str(e))

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
            InvokeConnectionError: [requests.exceptions.ConnectionError],
            InvokeServerUnavailableError: [requests.exceptions.Timeout],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [requests.exceptions.RequestException],
        }

    def _calc_response_usage(
        self, model: str, credentials: dict, tokens: int, total_tokens: int = None
    ) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: prompt tokens
        :param total_tokens: total tokens
        :return: usage
        """
        if total_tokens is None:
            total_tokens = tokens

        # Pricing from Mistral documentation: $0.1 per 1M tokens
        input_price_info = {
            "unit_price": Decimal("0.1"),
            "unit": Decimal("1000000"),  # per 1M tokens
            "currency": "USD",
        }

        unit_price = input_price_info["unit_price"]
        unit = input_price_info["unit"]
        total_price = Decimal(str(tokens)) * unit_price / unit

        return EmbeddingUsage(
            tokens=tokens,
            total_tokens=total_tokens,
            unit_price=unit_price,
            price_unit=unit,
            total_price=total_price,
            currency=input_price_info["currency"],
            latency=time.time() - time.time(),  # Will be set by the framework
        )
