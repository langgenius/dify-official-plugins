import json
import logging
import operator
from typing import Any, Optional

from dify_plugin import RerankModel
from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelType
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

from provider.sagemaker import get_sagemaker_client

logger = logging.getLogger(__name__)


class SageMakerRerankModel(RerankModel):
    """
    Model class for SageMaker rerank model.
    """

    def _sagemaker_rerank(
        self,
        query_input: str,
        docs: list[str],
        rerank_endpoint: str,
        sagemaker_client: Any,
    ):
        inputs = [query_input] * len(docs)
        response_model = sagemaker_client.invoke_endpoint(
            EndpointName=rerank_endpoint,
            Body=json.dumps({"inputs": inputs, "docs": docs}),
            ContentType="application/json",
        )
        json_str = response_model["Body"].read().decode("utf8")
        json_obj = json.loads(json_str)
        scores = json_obj["scores"]
        return scores if isinstance(scores, list) else [scores]

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
        :param top_n: top n
        :param user: unique user id
        :return: rerank result
        """
        try:
            if len(docs) == 0:
                return RerankResult(model=model, docs=docs)

            sagemaker_endpoint = credentials.get("sagemaker_endpoint")
            sagemaker_client = get_sagemaker_client("sagemaker-runtime", credentials)
            candidate_docs = []

            scores = self._sagemaker_rerank(
                query, docs, sagemaker_endpoint, sagemaker_client
            )
            for idx in range(len(scores)):
                candidate_docs.append({"content": docs[idx], "score": scores[idx]})

            sorted(candidate_docs, key=operator.itemgetter("score"), reverse=True)

            rerank_documents = []
            for idx, result in enumerate(candidate_docs):
                rerank_document = RerankDocument(
                    index=idx,
                    text=result.get("content"),
                    score=result.get("score", -100.0),
                )

                if score_threshold is not None:
                    if rerank_document.score >= score_threshold:
                        rerank_documents.append(rerank_document)
                else:
                    rerank_documents.append(rerank_document)

            return RerankResult(model=model, docs=rerank_documents)

        except Exception as e:
            logger.exception(f"Failed to invoke rerank model, model: {model}")
            raise InvokeError(
                f"Failed to invoke rerank model, model: {model}, error: {str(e)}"
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
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [InvokeBadRequestError, KeyError, ValueError],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        used to define customizable model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.RERANK,
            model_properties={},
            parameter_rules=[],
        )

        return entity
