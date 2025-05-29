from typing import Optional

import httpx

from dify_plugin import RerankModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelPropertyKey,
    ModelType,
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
from dify_plugin.entities.model.rerank import (
    RerankDocument,
    RerankResult,
)


class JinaRerankModel(RerankModel):
    """
    Model class for Jina rerank model.
    """

    api_base: str = "https://api.jina.ai/v1"

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
        api_key = credentials["api_key"]
        if not api_key:
            raise CredentialsValidateFailedError("api_key is required")

        if len(docs) == 0:
            return RerankResult(model=model, docs=[])

        base_url = credentials.get("base_url", self.api_base)
        base_url = base_url.removesuffix("/")

        url = base_url + "/rerank"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": model,
            "query": query,
            "documents": docs,
            "top_n": top_n,
        }

        try:
            response = httpx.post(url, headers=headers, json=data)
            response.raise_for_status()
            results = response.json()

            rerank_documents = []
            for result in results["results"]:
                rerank_document = RerankDocument(
                    index=result["index"],
                    text=result["document"]["text"],
                    score=result["relevance_score"],
                )
                if (
                    score_threshold is None
                    or result["relevance_score"] >= score_threshold
                ):
                    rerank_documents.append(rerank_document)

            return RerankResult(model=model, docs=rerank_documents)
        except httpx.HTTPStatusError as e:
            raise InvokeServerUnavailableError(str(e))

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
                    "Carson City is the capital city of the American state of Nevada. At the 2010 United States "
                    "Census, Carson City had a population of 55,274.",
                    "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that "
                    "are a political division controlled by the United States. Its capital is Saipan.",
                ],
                score_threshold=0.8,
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

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        generate custom model entities from credentials
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.RERANK,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size") or 0)
            },
        )

        return entity
