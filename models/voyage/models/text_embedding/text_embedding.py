import time
from json import JSONDecodeError, dumps
from typing import Optional

import requests
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (AIModelEntity, EmbeddingInputType,
                                        FetchFrom, ModelPropertyKey, ModelType,
                                        PriceType)
from dify_plugin.entities.model.text_embedding import (EmbeddingUsage,
                                                       TextEmbeddingResult)
from dify_plugin.errors.model import (CredentialsValidateFailedError,
                                      InvokeAuthorizationError,
                                      InvokeBadRequestError,
                                      InvokeConnectionError, InvokeError,
                                      InvokeRateLimitError,
                                      InvokeServerUnavailableError)
from dify_plugin.interfaces.model.text_embedding_model import \
    TextEmbeddingModel


class VoyageTextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for Voyage text embedding model.
    """

    api_base: str = "https://api.voyageai.com/v1"

    # Voyage accepts at most 1,000 texts per request, but the binding constraint is the
    # total token count, which differs by model. Anything not listed gets the tightest
    # published limit, since guessing high turns into a 400 mid-ingestion.
    max_texts_per_request: int = 1000
    default_token_limit: int = 120_000
    token_limits: dict[str, int] = {
        "voyage-4": 320_000,
        "voyage-4-lite": 1_000_000,
        "voyage-3.5": 320_000,
        "voyage-3.5-lite": 1_000_000,
        # voyage-4-large and voyage-context-4 are both 120K, i.e. the default.
    }
    # The gpt2 estimator is not Voyage's tokenizer, so leave headroom for it to
    # under-count. Splitting one extra request is much cheaper than a failed ingest.
    token_budget_margin: float = 0.8

    def _split_batches(self, model: str, texts: list[str]) -> list[list[str]]:
        """Split a batch into sub-batches that fit Voyage's per-request limits.

        Dify caps a batch at the model's `max_chunks`, but it has no idea how large
        those chunks are -- a knowledge base configured with 2,000-token segments can
        blow past the token limit well before the chunk count matters. Splitting here
        means `max_chunks` can be set for throughput without any risk of a 400.
        """
        budget = int(self.token_limits.get(model, self.default_token_limit) * self.token_budget_margin)

        batches: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        for text in texts:
            tokens = self._get_num_tokens_by_gpt2(text)
            # A single text over budget still goes on its own; the API will reject it
            # with a clearer message than anything invented here.
            if current and (current_tokens + tokens > budget or len(current) >= self.max_texts_per_request):
                batches.append(current)
                current, current_tokens = [], 0
            current.append(text)
            current_tokens += tokens
        if current:
            batches.append(current)
        return batches

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
        api_key = credentials["api_key"]
        if not api_key:
            raise CredentialsValidateFailedError("api_key is required")

        base_url = credentials.get("base_url", self.api_base)
        base_url = base_url.removesuffix("/")

        # The contextualised models take chunks grouped by document on a separate
        # endpoint; everything else uses the flat one.
        is_contextual = model.startswith("voyage-context-")
        url = base_url + ("/contextualizedembeddings" if is_contextual else "/embeddings")
        headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}

        # Check if this is a multimodal model
        is_multimodal = model.startswith("voyage-multimodal")
        image_url = credentials.get("image_url", "") if is_multimodal else ""
        image_base64 = credentials.get("image_base64", "") if is_multimodal else ""

        # Contextualising a batch is only meaningful when the texts are chunks of one
        # document. Dify does not tell the plugin where document boundaries fall, so
        # this stays opt-in -- and it never applies to a query, which has no siblings.
        contextualize_batch = (
            is_contextual
            and str(credentials.get("contextualize_batch", "")).lower() in ("true", "1", "yes")
            and input_type == EmbeddingInputType.DOCUMENT
        )

        embeddings: list[list[float]] = []
        total_tokens = 0

        for batch in self._split_batches(model, texts):
            # Prepare input data
            if is_contextual:
                # Each text is its own context group unless the batch is opted in.
                payload = {"inputs": [batch] if contextualize_batch else [[t] for t in batch]}
            elif is_multimodal and (image_url or image_base64):
                # Multimodal input format
                entries = []
                for text in batch:
                    entry = {"text": text}
                    if image_url:
                        entry["image_url"] = image_url
                    elif image_base64:
                        entry["image_base64"] = image_base64
                    entries.append([entry])
                payload = {"input": entries}
            else:
                # Standard text embedding model, or text-only for a multimodal one
                payload = {"input": batch}

            data = {"model": model, **payload}
            # Omit the key rather than sending the string "null", which the API rejects.
            if input_type is not None:
                data["input_type"] = input_type.value
            if credentials.get("output_dimension"):
                data["output_dimension"] = int(credentials["output_dimension"])
            if credentials.get("output_dtype"):
                data["output_dtype"] = credentials["output_dtype"]

            resp = self._post(url, headers, data)
            # The contextualised response nests one result object per input group.
            # Sort by index at both levels: embeddings must come back in input order
            # or every chunk in the batch is stored against the wrong segment.
            if is_contextual:
                rows = [
                    x
                    for group in sorted(resp["data"], key=lambda g: g["index"])
                    for x in sorted(group["data"], key=lambda x: x["index"])
                ]
            else:
                rows = sorted(resp["data"], key=lambda x: x["index"])
            embeddings.extend([float(v) for v in x["embedding"]] for x in rows)
            total_tokens += resp["usage"]["total_tokens"]

        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=total_tokens)

        return TextEmbeddingResult(model=model, embeddings=embeddings, usage=usage)

    def _post(self, url: str, headers: dict, data: dict) -> dict:
        """POST to Voyage and map transport and HTTP failures onto Dify's error types."""
        try:
            response = requests.post(url, headers=headers, data=dumps(data))
        except Exception as e:
            raise InvokeConnectionError(str(e))

        if response.status_code != 200:
            try:
                msg = response.json()["detail"]
                if response.status_code == 401:
                    raise InvokeAuthorizationError(msg)
                elif response.status_code == 429:
                    raise InvokeRateLimitError(msg)
                elif response.status_code == 500:
                    raise InvokeServerUnavailableError(msg)
                else:
                    raise InvokeBadRequestError(msg)
            except JSONDecodeError as e:
                raise InvokeServerUnavailableError(
                    f"Failed to convert response to json: {e} with text: {response.text}"
                )

        try:
            return response.json()
        except Exception as e:
            raise InvokeServerUnavailableError(f"Failed to convert response to json: {e} with text: {response.text}")

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return:
        """
        tokens = []
        for text in texts:
            tokens.append(self._get_num_tokens_by_gpt2(text))
        return tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._invoke(model=model, credentials=credentials, texts=["ping"])
        except Exception as e:
            raise CredentialsValidateFailedError(f"Credentials validation failed: {e}")

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [KeyError, InvokeBadRequestError],
        }

    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: input tokens
        :return: usage
        """
        # get input price info
        input_price_info = self.get_price(
            model=model, credentials=credentials, price_type=PriceType.INPUT, tokens=tokens
        )

        # transform usage
        usage = EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - self.started_at,
        )

        return usage

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        """
        generate custom model entities from credentials
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            model_type=ModelType.TEXT_EMBEDDING,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size"))},
        )

        return entity
