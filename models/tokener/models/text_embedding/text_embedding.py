import base64
import math
import re
from decimal import Decimal

import tiktoken
from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
    MultiModalEmbeddingResult,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeServerUnavailableError
from dify_plugin.interfaces.model.openai_compatible.text_embedding import OAICompatEmbeddingModel

from models._api import TokenerAPIModel
from models.llm._openai_responses import count_text

TONGYI_MULTIMODAL = {"qwen3-vl-embedding", "multimodal-embedding-v1"}


def _vectors(response, count, dimensions=None):
    data = response.get("data")
    if (
        count == 1
        and isinstance(data, list)
        and len(data) == 1
        and isinstance(data[0], dict)
        and data[0].get("index", -1) is None
    ):
        data = [{**data[0], "index": 0}]
    if (
        not isinstance(data, list)
        or len(data) != count
        or any(not isinstance(item, dict) or type(item.get("index")) is not int for item in data)
        or sorted(item["index"] for item in data) != list(range(count))
    ):
        raise InvokeServerUnavailableError("Tokener.ai returned invalid embedding indices")
    vectors = []
    for item in sorted(data, key=lambda item: item["index"]):
        vector = item.get("embedding")
        if (
            not isinstance(vector, list)
            or not vector
            or any(type(value) not in {int, float} or not math.isfinite(value) for value in vector)
            or (dimensions is not None and len(vector) != dimensions)
        ):
            raise InvokeServerUnavailableError("Tokener.ai returned invalid embedding vectors")
        dimensions = len(vector)
        vectors.append(vector)
    return vectors, dimensions


class TokenerTextEmbeddingModel(TokenerAPIModel, OAICompatEmbeddingModel):
    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        if not model.startswith("text-embedding-3") and model != "text-embedding-ada-002":
            return super().get_num_tokens(model, credentials, texts)
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return [len(encoding.encode(text)) for text in texts]

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
        if model == "gemini-embedding-001":
            return self._gemini_text(model, credentials, texts, input_type)
        chunks = None
        if model.startswith("text-embedding-3") or model == "text-embedding-ada-002":
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
            context = self._get_context_size(model, credentials)
            chunks = []
            for index, text in enumerate(texts):
                encoded = encoding.encode(text)
                chunks.extend(
                    (index, encoded[start : start + context])
                    for start in range(0, len(encoded), context)
                )
        inputs = [chunk for _, chunk in chunks] if chunks is not None else texts
        if model.startswith("text-embedding-v") or model in TONGYI_MULTIMODAL:
            context = self._get_context_size(model, credentials)
            inputs = [
                text[: len(text) * context // count] if count >= context else text
                for text in texts
                for count in [self._get_num_tokens_by_gpt2(text)]
            ]
        if model in TONGYI_MULTIMODAL:
            vectors, usage = self._tongyi_embeddings(
                model, credentials, [{"text": text} for text in inputs]
            )
            return TextEmbeddingResult(model=model, embeddings=vectors, usage=usage)
        embeddings = []
        tokens = 0
        dimensions = None
        batch_size = self._get_max_chunks(model, credentials)
        for offset in range(0, len(inputs), batch_size):
            batch = inputs[offset : offset + batch_size]
            payload = {"model": model, "input": batch, "encoding_format": "float"}
            if model == "gemini-embedding-2-preview":
                prefix = (
                    "task: search result | query: "
                    if input_type == EmbeddingInputType.QUERY
                    else "title: none | text: "
                )
                payload["input"] = [prefix + text for text in batch]
            elif model in {"embed-english-v3", "embed-multilingual-v3", "embed-v4"}:
                payload["input_type"] = (
                    "search_query" if input_type == EmbeddingInputType.QUERY else "search_document"
                )
            if user:
                payload["user"] = user
            response = self._post("embeddings", credentials, payload)
            vectors, dimensions = _vectors(response, len(batch), dimensions)
            embeddings.extend(vectors)
            used = response["usage"]["total_tokens"]
            if type(used) is not int or used < 0:
                raise InvokeServerUnavailableError("Tokener.ai returned invalid embedding usage")
            tokens += used
        if chunks is not None:
            by_text = [[] for _ in texts]
            for (index, chunk), vector in zip(chunks, embeddings, strict=True):
                by_text[index].append((len(chunk), vector))
            embeddings = []
            for group in by_text:
                total = sum(weight for weight, _ in group)
                average = [
                    math.fsum(weight * vector[i] for weight, vector in group) / total
                    for i in range(dimensions)
                ]
                norm = math.sqrt(math.fsum(value * value for value in average))
                if not norm or not math.isfinite(norm):
                    raise InvokeServerUnavailableError("Cannot normalize embedding vector")
                embeddings.append([value / norm for value in average])
        return TextEmbeddingResult(
            model=model,
            embeddings=embeddings,
            usage=self._calc_response_usage(model, credentials, tokens),
        )

    def _tongyi_embeddings(self, model, credentials, inputs):
        embeddings, tokens, text_tokens, image_tokens, dimensions = [], 0, 0, 0, None
        for item in inputs:
            response = self._post("embeddings", credentials, {"model": model, "input": [item]})
            vectors, dimensions = _vectors(response, 1, dimensions)
            embeddings.extend(vectors)
            usage = response.get("usage") or {}
            total = usage.get("total_tokens")
            details = usage.get("prompt_tokens_details") or {}
            text = details.get("text_tokens", total if "text" in item else None)
            image = details.get("image_tokens", 0 if "text" in item else None)
            if any(type(value) is not int or value < 0 for value in (total, text, image)):
                raise InvokeServerUnavailableError("Tokener.ai returned invalid embedding usage")
            if text + image != total:
                raise InvokeServerUnavailableError(
                    "Tokener.ai returned inconsistent embedding usage"
                )
            tokens += total
            text_tokens += text
            image_tokens += image
        usage = self._calc_response_usage(model, credentials, tokens)
        if model == "qwen3-vl-embedding" and image_tokens:
            usage.total_price = (
                usage.unit_price
                * usage.price_unit
                * (Decimal(text_tokens) + Decimal("2.58") * image_tokens)
            )
        return embeddings, usage

    def _gemini_text(self, model, credentials, texts, input_type):
        context = self._get_context_size(model, credentials)
        chunks = []
        for index, text in enumerate(texts):
            pending = [text]
            while pending:
                text = pending.pop()
                payload = {"contents": [{"role": "user", "parts": [{"text": text}]}]}
                with self._request_at(
                    f"/v1beta/models/{model}:countTokens", credentials, json=payload
                ) as response:
                    result = response.json()
                count = result.get("totalTokens") if isinstance(result, dict) else None
                if count is None or type(count) is not int or count < 0:
                    raise InvokeServerUnavailableError("Invalid Gemini token count")
                count = count or self._get_num_tokens_by_gpt2(text)
                if count < context or len(text) <= 1:
                    chunks.append((index, text, count))
                    continue
                cutoff = min(max(1, len(text) * context // count), len(text) - 1)
                for pattern in (r"[.!?]", r",", r"\s"):
                    if match := re.search(pattern, text[cutoff:]):
                        boundary = cutoff + match.start() + 1
                        if boundary < len(text):
                            cutoff = boundary
                        break
                pending.extend([text[cutoff:], text[:cutoff]])
        parts = [{"text": text} for _, text, _ in chunks]
        data = self._gemini_embeddings(model, credentials, parts, input_type)
        groups = [[] for _ in texts]
        tokens = 0
        for (index, _, estimated), (vector, count) in zip(chunks, data, strict=True):
            groups[index].append((vector, count))
            tokens += count or estimated
        embeddings = []
        for group in groups:
            if len(group) == 1:
                embeddings.append(group[0][0])
                continue
            weighted = all(count is not None for _, count in group)
            weights = [count if weighted else 1 for _, count in group]
            average = [
                math.fsum(
                    vector[i] * weight for (vector, _), weight in zip(group, weights, strict=True)
                )
                for i in range(len(group[0][0]))
            ]
            norm = math.sqrt(math.fsum(value * value for value in average))
            if not norm or not math.isfinite(norm):
                raise InvokeServerUnavailableError("Cannot normalize Gemini embedding vector")
            embeddings.append([value / norm for value in average])
        return TextEmbeddingResult(
            model=model,
            embeddings=embeddings,
            usage=self._calc_response_usage(model, credentials, tokens),
        )

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        documents: list[MultiModalContent],
        user: str | None = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> MultiModalEmbeddingResult:
        if model in TONGYI_MULTIMODAL:
            inputs = []
            for document in documents:
                if document.content_type == MultiModalContentType.TEXT:
                    inputs.append({"text": document.content})
                    continue
                if document.content_type != MultiModalContentType.IMAGE:
                    raise InvokeBadRequestError(
                        "Tongyi embeddings support text, PNG, JPEG, and BMP"
                    )
                data = document.content.split(",", 1)[-1]
                try:
                    decoded = base64.b64decode(data, validate=True)
                except ValueError as error:
                    raise InvokeBadRequestError("Tongyi image must contain valid base64") from error
                mime = next(
                    (
                        name
                        for header, name in (
                            (b"\x89PNG\r\n\x1a\n", "png"),
                            (b"\xff\xd8\xff", "jpeg"),
                            (b"BM", "bmp"),
                        )
                        if decoded.startswith(header)
                    ),
                    None,
                )
                if mime is None:
                    raise InvokeBadRequestError(
                        "Tongyi embeddings support PNG, JPEG, and BMP images"
                    )
                inputs.append({"image": f"data:image/{mime};base64,{data}"})
            vectors, usage = self._tongyi_embeddings(model, credentials, inputs)
            return MultiModalEmbeddingResult(model=model, embeddings=vectors, usage=usage)
        if model != "gemini-embedding-2-preview":
            raise InvokeBadRequestError("This model does not support multimodal embeddings")
        if all(document.content_type == MultiModalContentType.TEXT for document in documents):
            result = self._invoke(
                model,
                credentials,
                [document.content for document in documents],
                user,
                input_type,
            )
            return MultiModalEmbeddingResult(
                model=result.model,
                embeddings=result.embeddings,
                usage=result.usage,
            )
        parts = []
        for document in documents:
            if document.content_type == MultiModalContentType.TEXT:
                parts.append({"text": document.content})
                continue
            if document.content_type != MultiModalContentType.IMAGE:
                raise InvokeBadRequestError("Gemini embeddings support text, PNG, and JPEG")
            data = (
                document.content.partition(",")[2]
                if document.content.startswith("data:")
                else document.content
            )
            try:
                decoded = base64.b64decode(data, validate=True)
            except ValueError as error:
                raise InvokeBadRequestError("Gemini image must contain valid base64") from error
            if decoded.startswith(b"\x89PNG\r\n\x1a\n"):
                mime_type = "image/png"
            elif decoded.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            else:
                raise InvokeBadRequestError("Gemini embeddings support PNG and JPEG images")
            parts.append({"inlineData": {"mimeType": mime_type, "data": data}})

        data = self._gemini_embeddings(model, credentials, parts, input_type)
        tokens = sum(
            count
            if count is not None
            else count_text(model, part["text"])
            if "text" in part
            else 258
            for part, (_, count) in zip(parts, data, strict=True)
        )
        return MultiModalEmbeddingResult(
            model=model,
            embeddings=[vector for vector, _ in data],
            usage=self._calc_response_usage(model, credentials, tokens),
        )

    def _gemini_embeddings(self, model, credentials, parts, input_type):
        task = "RETRIEVAL_QUERY" if input_type == EmbeddingInputType.QUERY else "RETRIEVAL_DOCUMENT"
        batch_size = min(self._get_max_chunks(model, credentials), 100)
        batches = [
            parts[offset : offset + batch_size] for offset in range(0, len(parts), batch_size)
        ]
        if any(sum("inlineData" in part for part in batch) > 6 for batch in batches):
            raise InvokeBadRequestError("Gemini permits up to six images per embedding batch")
        embeddings = []
        dimensions = None
        for batch in batches:
            payload = {
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"role": "user", "parts": [part]},
                        "taskType": task,
                    }
                    for part in batch
                ]
            }
            with self._request_at(
                f"/v1beta/models/{model}:batchEmbedContents", credentials, json=payload
            ) as response:
                result = response.json()
            data = result.get("embeddings") if isinstance(result, dict) else None
            if not isinstance(data, list) or len(data) != len(batch):
                raise InvokeServerUnavailableError(
                    "Tokener.ai returned an invalid Gemini embedding batch"
                )
            for item in data:
                vector = item.get("values") if isinstance(item, dict) else None
                if (
                    not isinstance(vector, list)
                    or not vector
                    or any(
                        type(value) not in (float, int) or not math.isfinite(value)
                        for value in vector
                    )
                    or dimensions is not None
                    and len(vector) != dimensions
                ):
                    raise InvokeServerUnavailableError(
                        "Tokener.ai returned invalid embedding vectors"
                    )
                dimensions = len(vector)
                count = (item.get("statistics") or {}).get("tokenCount")
                if count is not None and (type(count) is not int or count < 0):
                    raise InvokeServerUnavailableError("Invalid Gemini embedding token count")
                embeddings.append((vector, count))
        return embeddings
