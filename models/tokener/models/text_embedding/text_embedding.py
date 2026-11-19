import base64
import math

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


class TokenerTextEmbeddingModel(TokenerAPIModel, OAICompatEmbeddingModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: str | None = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        embeddings = []
        tokens = 0
        dimensions = None
        batch_size = self._get_max_chunks(model, credentials)
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            payload = {"model": model, "input": batch, "encoding_format": "float"}
            if model == "gemini-embedding-001":
                payload["task_type"] = (
                    "RETRIEVAL_QUERY"
                    if input_type == EmbeddingInputType.QUERY
                    else "RETRIEVAL_DOCUMENT"
                )
            elif model == "gemini-embedding-2-preview":
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
            data = response.get("data")
            if (
                len(batch) == 1
                and isinstance(data, list)
                and len(data) == 1
                and isinstance(data[0], dict)
                and "index" in data[0]
                and data[0]["index"] is None
            ):
                data = [{**data[0], "index": 0}]
            if (
                not isinstance(data, list)
                or len(data) != len(batch)
                or any(
                    not isinstance(item, dict) or type(item.get("index")) is not int
                    for item in data
                )
                or sorted(item["index"] for item in data) != list(range(len(batch)))
            ):
                raise InvokeServerUnavailableError("Tokener.ai returned invalid embedding indices")
            for item in sorted(data, key=lambda item: item["index"]):
                vector = item["embedding"]
                if (
                    not isinstance(vector, list)
                    or not vector
                    or any(type(v) not in {int, float} or not math.isfinite(v) for v in vector)
                    or (dimensions is not None and len(vector) != dimensions)
                ):
                    raise InvokeServerUnavailableError(
                        "Tokener.ai returned invalid embedding vectors"
                    )
                dimensions = len(vector)
                embeddings.append(vector)
            used = response["usage"]["total_tokens"]
            if type(used) is not int or used < 0:
                raise InvokeServerUnavailableError("Tokener.ai returned invalid embedding usage")
            tokens += used
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
        task = "RETRIEVAL_QUERY" if input_type == EmbeddingInputType.QUERY else "RETRIEVAL_DOCUMENT"
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

        batch_size = min(self._get_max_chunks(model, credentials), 100)
        batches = [
            parts[offset : offset + batch_size] for offset in range(0, len(parts), batch_size)
        ]
        if any(sum("inlineData" in part for part in batch) > 6 for batch in batches):
            raise InvokeBadRequestError("Gemini permits up to six images per embedding batch")
        embeddings = []
        tokens = 0
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
            for item, part in zip(data, batch, strict=True):
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
                embeddings.append(vector)
                count = (item.get("statistics") or {}).get("tokenCount")
                if type(count) is int and count >= 0:
                    tokens += count
                else:
                    tokens += count_text(model, part["text"]) if "text" in part else 258
        return MultiModalEmbeddingResult(
            model=model,
            embeddings=embeddings,
            usage=self._calc_response_usage(model, credentials, tokens),
        )
