import time
from math import fsum, isfinite, sqrt

import tiktoken
from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
)
from openai import OpenAI

from ..common_openai import _CommonOpenAI


def _normalize(embedding: list[float]) -> list[float]:
    norm = sqrt(fsum(value * value for value in embedding))
    if not norm or not isfinite(norm):
        raise ValueError("Cannot normalize a zero or non-finite embedding")

    normalized = [value / norm for value in embedding]
    if not all(isfinite(value) for value in normalized):
        raise ValueError("Cannot normalize a non-finite embedding")
    return normalized


def _merge_embeddings(
    embeddings: list[list[float]], token_counts: list[int]
) -> list[float]:
    total_tokens = sum(token_counts)
    if not embeddings or total_tokens <= 0:
        raise ValueError("Cannot merge embeddings without tokens")

    average = [
        fsum(
            value * token_count
            for value, token_count in zip(values, token_counts, strict=True)
        )
        / total_tokens
        for values in zip(*embeddings, strict=True)
    ]
    return _normalize(average)


class OpenAITextEmbeddingModel(_CommonOpenAI, TextEmbeddingModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: str | None = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        if not texts or any(not text for text in texts):
            raise InvokeBadRequestError("Embedding input must not be empty")

        client = OpenAI(**self._to_credential_kwargs(credentials))
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        chunks: list[tuple[int, list[int]]] = []
        for text_index, text in enumerate(texts):
            tokens = encoding.encode(text)
            chunks.extend(
                (text_index, tokens[start : start + context_size])
                for start in range(0, len(tokens), context_size)
            )

        embeddings_by_text: list[list[list[float]]] = [[] for _ in texts]
        token_counts_by_text: list[list[int]] = [[] for _ in texts]
        used_tokens = 0

        for start in range(0, len(chunks), max_chunks):
            batch = chunks[start : start + max_chunks]
            batch_embeddings, batch_tokens = self._embedding_invoke(
                model=model,
                client=client,
                texts=[tokens for _, tokens in batch],
                user=user,
            )
            used_tokens += batch_tokens
            for (text_index, tokens), embedding in zip(
                batch, batch_embeddings, strict=True
            ):
                embeddings_by_text[text_index].append(embedding)
                token_counts_by_text[text_index].append(len(tokens))

        embeddings: list[list[float]] = []
        for text_embeddings, token_counts in zip(
            embeddings_by_text, token_counts_by_text, strict=True
        ):
            embeddings.append(_merge_embeddings(text_embeddings, token_counts))

        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=used_tokens
        )

        return TextEmbeddingResult(embeddings=embeddings, usage=usage, model=model)

    def get_num_tokens(
        self, model: str, credentials: dict, texts: list[str]
    ) -> list[int]:
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return [len(encoding.encode(text)) for text in texts]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self._embedding_invoke(
                model=model,
                client=OpenAI(**self._to_credential_kwargs(credentials)),
                texts=["ping"],
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def _embedding_invoke(
        self,
        model: str,
        client: OpenAI,
        texts: str | list[str] | list[list[int]],
        user: str | None = None,
    ) -> tuple[list[list[float]], int]:
        request_kwargs = {"user": user} if user else {}
        response = client.embeddings.create(
            input=texts,
            model=model,
            encoding_format="float",
            **request_kwargs,
        )
        return [data.embedding for data in response.data], response.usage.total_tokens

    def _calc_response_usage(
        self, model: str, credentials: dict, tokens: int
    ) -> EmbeddingUsage:
        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens,
        )

        return EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - self.started_at,
        )
