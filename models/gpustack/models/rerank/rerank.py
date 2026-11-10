import math

import requests
from dify_plugin import RerankModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
)
from dify_plugin.entities.model.rerank import (
    MultiModalRerankResult,
    RerankDocument,
    RerankResult,
)
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models.multimodal import api_base_url, content_part, post_json, require_vision


class GPUStackRerankModel(RerankModel):
    """
    Model class for GPUStack rerank model.
    """

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    def _invoke(
        self,
        model: str,
        credentials: dict,
        query: str,
        docs: list[str],
        score_threshold: float | None = None,
        top_n: int | None = None,
        user: str | None = None,
    ) -> RerankResult:
        """
        Invoke rerank model

        :param model: model name
        :param credentials: model credentials
        :param query: search query
        :param docs: docs for reranking
        :param score_threshold: score threshold
        :param top_n: top n documents to return
        :param user: unique user id
        :return: rerank result
        """
        # Preserve the legacy default of three results for text-only callers.
        limit = 3 if top_n is None else top_n
        ranked = self._request_rerank(
            model, credentials, query, docs, docs, limit, score_threshold, True
        )
        return RerankResult(model=model.strip(), docs=ranked)

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        query: MultiModalContent,
        docs: list[MultiModalContent],
        score_threshold: float | None = None,
        top_n: int | None = None,
        user: str | None = None,
    ) -> MultiModalRerankResult:
        """Use the content-block rerank protocol while preserving candidate positions."""
        require_vision(credentials)
        limit = len(docs) if top_n is None else top_n
        if not docs or limit == 0:
            return MultiModalRerankResult(model=model, docs=[])
        query_part = content_part(query)
        query_payload = (
            query.content
            if query.content_type == MultiModalContentType.TEXT
            else {"content": [query_part]}
        )
        documents = [{"content": [content_part(doc)]} for doc in docs]
        ranked = self._request_rerank(
            model,
            credentials,
            query_payload,
            documents,
            [doc.content for doc in docs],
            limit,
            score_threshold,
        )
        return MultiModalRerankResult(model=model, docs=ranked)

    def _request_rerank(
        self,
        model: str,
        credentials: dict,
        query: str | dict,
        documents: list,
        original_contents: list[str],
        top_n: int,
        score_threshold: float | None,
        use_returned_text: bool = False,
    ) -> list[RerankDocument]:
        """Validate indexes before mapping scores back to the original inputs."""
        if type(top_n) is not int or top_n < 0:
            raise InvokeBadRequestError("top_n must be a non-negative integer")
        if score_threshold is not None and not math.isfinite(score_threshold):
            raise InvokeBadRequestError("score_threshold must be finite")
        if not documents or top_n == 0:
            return []
        payload = {
            "model": credentials.get("endpoint_model_name") or model.strip(),
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        result = post_json(
            api_base_url(credentials) + "/rerank",
            credentials,
            payload,
            default_timeout=10,
        )
        results = result.get("results")
        if not isinstance(results, list):
            raise InvokeError("GPUStack returned invalid rerank results")
        seen = set()
        ranked = []
        for item in results:
            if not isinstance(item, dict):
                raise InvokeError("GPUStack returned an invalid rerank entry")
            index = item.get("index")
            score = item.get("relevance_score")
            if (
                type(index) is not int
                or not 0 <= index < len(original_contents)
                or index in seen
            ):
                raise InvokeError(
                    "GPUStack returned an invalid or duplicate rerank index"
                )
            if type(score) not in (int, float) or not math.isfinite(score):
                raise InvokeError("GPUStack returned an invalid rerank score")
            seen.add(index)
            text = original_contents[index]
            if use_returned_text and "document" in item:
                document = item["document"]
                if not isinstance(document, dict) or not isinstance(
                    document.get("text"), str
                ):
                    raise InvokeError("GPUStack returned an invalid rerank document")
                text = document["text"]
            if score_threshold is None or score >= score_threshold:
                ranked.append(RerankDocument(index=index, text=text, score=score))
        ranked.sort(key=lambda doc: doc.score, reverse=True)
        return ranked[:top_n]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        query = "What is the capital of the United States?"
        docs = [
            "Carson City is the capital city of the American state of Nevada. At the 2010 United States Census, Carson City had a population of 55,274.",
            "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that are a political division controlled by the United States. Its capital is Saipan.",
        ]
        try:
            if credentials.get("vision_support") == "support":
                self.invoke_multimodal(
                    model=model,
                    credentials=credentials,
                    query=MultiModalContent(
                        content=query, content_type=MultiModalContentType.TEXT
                    ),
                    docs=[
                        MultiModalContent(
                            content=doc, content_type=MultiModalContentType.TEXT
                        )
                        for doc in docs
                    ],
                    score_threshold=0.8,
                )
            else:
                self._invoke(
                    model=model,
                    credentials=credentials,
                    query=query,
                    docs=docs,
                    score_threshold=0.8,
                )
        except (InvokeError, KeyError, TypeError, ValueError) as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeConnectionError: [requests.ConnectionError, requests.Timeout],
            InvokeServerUnavailableError: [],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        generate custom model entities from credentials
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            model_type=ModelType.RERANK,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 512))
            },
        )
        if credentials.get("vision_support") == "support":
            entity.features = [ModelFeature.VISION]
        return entity
