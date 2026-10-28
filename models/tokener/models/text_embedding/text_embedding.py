import math

from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult
from dify_plugin.errors.model import InvokeServerUnavailableError
from dify_plugin.interfaces.model.openai_compatible.text_embedding import OAICompatEmbeddingModel

from models._api import TokenerAPIModel


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
            if model == "gemini-embedding-2-preview":
                prefix = (
                    "task: search result | query: "
                    if input_type == EmbeddingInputType.QUERY
                    else "title: none | text: "
                )
                payload["input"] = [prefix + text for text in batch]
            # Dify's Gemini provider does not send the console user ID to
            # embedContent. Gemini routes reject this OpenAI-only metadata;
            # tenancy and billing remain scoped by the managed API key.
            if user and model not in {"gemini-embedding-001", "gemini-embedding-2-preview"}:
                payload["user"] = user
            response = self._post("embeddings", credentials, payload)
            data = response["data"]
            # Only one input and one explicit null index are unambiguous. Never
            # infer ordering for batches, missing fields or other invalid indices.
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
