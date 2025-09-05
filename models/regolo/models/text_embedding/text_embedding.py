import json
from decimal import Decimal
from typing import Optional
from urllib.parse import urljoin

import requests
from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    PriceConfig,
)
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.text_embedding_model import TextEmbeddingModel


class RegoloEmbeddingModel(TextEmbeddingModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        headers = {"Content-Type": "application/json"}
        api_key = credentials.get("regolo_api_key") or credentials.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        endpoint_url = credentials.get("endpoint_url", "https://api.regolo.ai/v1/")
        if not endpoint_url.endswith("/"):
            endpoint_url += "/"
        endpoint_url = urljoin(endpoint_url, "embeddings")

        payload = {"input": texts, "model": model}
        response = requests.post(endpoint_url, headers=headers, data=json.dumps(payload), timeout=(10, 300))
        response.raise_for_status()
        result = response.json()

        embeddings = [item["embedding"] for item in result.get("data", [])]
        usage_tokens = result.get("usage", {}).get("total_tokens", 0)

        usage = EmbeddingUsage(
            tokens=usage_tokens,
            total_tokens=usage_tokens,
            unit_price=Decimal("0"),
            price_unit=Decimal("0"),
            total_price=Decimal("0"),
            currency="EUR",
            latency=0.0,
        )
        return TextEmbeddingResult(embeddings=embeddings, usage=usage, model=model)

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.TEXT_EMBEDDING,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 8192)),
                ModelPropertyKey.MAX_CHUNKS: 1,
            },
            parameter_rules=[],
            pricing=PriceConfig(
                input=Decimal(credentials.get("input_price", 0)),
                unit=Decimal(credentials.get("unit", 0)),
                currency=credentials.get("currency", "EUR"),
            ),
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            headers = {"Content-Type": "application/json"}
            api_key = credentials.get("regolo_api_key") or credentials.get("api_key")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            endpoint_url = credentials.get("endpoint_url", "https://api.regolo.ai/v1/")
            if not endpoint_url.endswith("/"):
                endpoint_url += "/"
            endpoint_url = urljoin(endpoint_url, "embeddings")

            payload = {"input": "ping", "model": model}
            resp = requests.post(endpoint_url, headers=headers, data=json.dumps(payload), timeout=(10, 300))
            if resp.status_code != 200:
                raise CredentialsValidateFailedError(
                    f"Credentials validation failed with status code {resp.status_code}"
                )
            _ = resp.json()
        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        """Rough token estimator: ~1 token per 4 chars for each text."""
        tokens: list[int] = []
        for text in texts:
            tokens.append(max(1, len(text) // 4))
        return tokens

    def _invoke_error_mapping(self, status_code: int, response_text: str) -> str:
        """Map HTTP status codes to readable messages for embeddings API."""
        if status_code == 401:
            return "Unauthorized: check regolo_api_key"
        if status_code == 403:
            return "Forbidden: API key lacks permission"
        if status_code == 404:
            return "Not found: embeddings endpoint or model invalid"
        if status_code == 429:
            return "Rate limited: too many requests"
        if 500 <= status_code < 600:
            return "Server error from Regolo API"
        return f"HTTP {status_code}: {response_text[:200]}"

