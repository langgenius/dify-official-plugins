from typing import Optional
import httpx
from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelPropertyKey, ModelType
from dify_plugin.entities.model.rerank import RerankDocument, RerankResult
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.rerank_model import RerankModel


def base_rerank(model: str,
                credentials: dict,
                query: str,
                docs: list[str],
                score_threshold: Optional[float] = None,
                top_n: Optional[int] = None,
                user: Optional[str] = None, ):
    base_url = credentials.get("base_url", "https://ai.gitee.com/v1")
    base_url = base_url.removesuffix("/") + "/rerank"
    try:
        body = {"model": model, "query": query, "documents": docs}
        if top_n is not None:
            body["top_n"] = top_n
        response = httpx.post(
            base_url,
            json=body,
            headers={"Authorization": f"Bearer {credentials.get('api_key')}"},
        )
        response.raise_for_status()
        results = response.json()
        rerank_documents = []
        for result in results["results"]:
            rerank_document = RerankDocument(
                index=result["index"], text=result["document"]["text"], score=result["relevance_score"]
            )
            if score_threshold is None or result["relevance_score"] >= score_threshold:
                rerank_documents.append(rerank_document)
        return RerankResult(model=model, docs=rerank_documents)
    except httpx.HTTPStatusError as e:
        raise InvokeServerUnavailableError(str(e))


def multi_modal_rerank(model, credentials, query, docs, score_threshold, top_n, user):
    base_url = credentials.get("base_url", "https://ai.gitee.com/v1")
    base_url = base_url.removesuffix("/") + "/rerank/multimodal"
    try:
        # we should convert ["A", "B"] to [{"text": "A"}, {"text": "B"}]
        documents = [{"text": item} for item in docs]
        body = {"model": model, "query": {"text": query}, "documents": documents, "return_documents": True}
        response = httpx.post(
            base_url,
            json=body,
            headers={"Authorization": f"Bearer {credentials.get('api_key')}"},
        )
        response.raise_for_status()
        results = response.json()
        rerank_documents = []
        for result in results:
            index = int(result["index"]) - 1
            rerank_document = RerankDocument(
                index=index, text=result["document"]["text"], score=result["score"]
            )
            if score_threshold is None or result["score"] >= score_threshold:
                rerank_documents.append(rerank_document)
        return RerankResult(model=model, docs=rerank_documents)
    except httpx.HTTPStatusError as e:
        raise InvokeServerUnavailableError(str(e))


class GiteeAIRerankModel(RerankModel):
    # multiModals
    multiModalModels = ['jina-reranker-m0']

    """
    Model class for rerank model.
    """

    def _invoke(
            self,
            model: str,
            credentials: dict,
            query: str,
            docs: list[str],
            score_threshold: Optional[float] = None,
            top_n: Optional[int] = None,
            user: Optional[str] = None,
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
        if len(docs) == 0:
            return RerankResult(model=model, docs=[])

        # use multi_modal_rerank if the model is multi-modal
        if model in GiteeAIRerankModel.multiModalModels:
            return multi_modal_rerank(
                model=model,
                credentials=credentials,
                query=query,
                docs=docs,
                score_threshold=score_threshold,
                top_n=top_n,
                user=user,
            )
        else:
            return base_rerank(
                model=model,
                credentials=credentials,
                query=query,
                docs=docs,
                score_threshold=score_threshold,
                top_n=top_n,
                user=user,
            )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._invoke(
                model=model,
                credentials=credentials,
                query="What is the capital of the United States?",
                docs=[
                    "Carson City is the capital city of the American state of Nevada. At the 2010 United States Census, Carson City had a population of 55,274.",
                    "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that are a political division controlled by the United States. Its capital is Saipan.",
                ],
                score_threshold=0.01,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeConnectionError: [httpx.ConnectError],
            InvokeServerUnavailableError: [httpx.RemoteProtocolError],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [httpx.HTTPStatusError],
            InvokeBadRequestError: [httpx.RequestError],
        }

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        """
        generate custom model entities from credentials
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.RERANK,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 512))},
        )
        return entity
