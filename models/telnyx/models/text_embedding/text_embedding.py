from __future__ import annotations

import time
from typing import Optional

from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, TextEmbeddingResult
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError

from ..common_telnyx import _CommonTelnyx


class TelnyxTextEmbeddingModel(_CommonTelnyx, TextEmbeddingModel):
    """Telnyx OpenAI-compatible embeddings endpoint."""

    EMBEDDINGS_PATH = "/v2/ai/openai/embeddings"

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        payload = {"model": model, "input": texts}
        if user:
            payload["user"] = user
        response = self._post_json(credentials, self.EMBEDDINGS_PATH, payload)
        data = response.json()
        rows = data.get("data") or []
        if len(rows) != len(texts):
            raise InvokeBadRequestError("Telnyx embedding response size does not match input size")
        rows = sorted(rows, key=lambda row: row.get("index", 0))
        embeddings = [list(map(float, row["embedding"])) for row in rows]
        usage_data = data.get("usage") or {}
        tokens = int(usage_data.get("total_tokens") or usage_data.get("prompt_tokens") or sum(self.get_num_tokens(model, credentials, texts)))
        return TextEmbeddingResult(
            embeddings=embeddings,
            usage=self._calc_embedding_usage(model, credentials, tokens),
            model=data.get("model") or model,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self._invoke(model=model, credentials=credentials, texts=["ping"])
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        counts = []
        for text in texts:
            try:
                counts.append(self._get_num_tokens_by_gpt2(text))
            except Exception:
                counts.append(max(1, len(text) // 4) if text else 0)
        return counts

    def _calc_embedding_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        try:
            price = self.get_price(model=model, credentials=credentials, price_type=PriceType.INPUT, tokens=tokens)
            return EmbeddingUsage(
                tokens=tokens,
                total_tokens=tokens,
                unit_price=price.unit_price,
                price_unit=price.unit,
                total_price=price.total_amount,
                currency=price.currency,
                latency=time.perf_counter() - self.started_at,
            )
        except Exception:
            return EmbeddingUsage(
                tokens=tokens,
                total_tokens=tokens,
                unit_price=0,
                price_unit=0,
                total_price=0,
                currency="USD",
                latency=time.perf_counter() - self.started_at,
            )
