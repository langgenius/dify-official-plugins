import json
import logging
import os
import ssl
import urllib.request
from typing import Optional

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
from dify_plugin.interfaces.model.rerank_model import RerankModel

logger = logging.getLogger(__name__)


class AzureRerankModel(RerankModel):
    """
    Model class for Azure AI Studio rerank model.
    """

    def _allow_self_signed_https(self, allowed):
        if (
            allowed
            and (not os.environ.get("PYTHONHTTPSVERIFY", ""))
            and getattr(ssl, "_create_unverified_context", None)
        ):
            ssl._create_default_https_context = ssl._create_unverified_context

    def _azure_rerank(self, query_input: str, docs: list[str], endpoint: str, api_key: str, model_name: Optional[str] = None, top_n: Optional[int] = None):
        # Azure AI Foundry may use different endpoint paths depending on the model
        # Common patterns: /v2/rerank (Cohere), /v1/rerank, /rerank, /score
        if not any(path in endpoint for path in ["/v2/rerank", "/v1/rerank", "/rerank", "/score"]):
            if endpoint.endswith(".models.ai.azure.com") or endpoint.endswith(".models.ai.azure.com/"):
                # Default to v2/rerank for Cohere models, which is the most common
                if not endpoint.endswith("/"):
                    endpoint += "/"
                endpoint += "v2/rerank"
        
        logger.info(f"Attempting rerank with endpoint: {endpoint}")
        
        # Build request data 
        data = {
            "query": query_input, 
            "documents": docs
        }
        
        # Add model field if provided or if using Cohere endpoint
        # Cohere models on Azure require "model" field
        if model_name:
            data["model"] = model_name
        elif "cohere" in endpoint.lower() or "/v2/rerank" in endpoint:
            # Auto-detect Cohere models and add required model field
            data["model"] = "model"
        
        if top_n is not None:
            data["top_n"] = top_n
        body = json.dumps(data).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req = urllib.request.Request(endpoint, body, headers)
        try:
            with urllib.request.urlopen(req) as response:
                result = response.read()
                return json.loads(result)
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf8", "ignore")
            logger.error(f"The request failed with status code: {error.code}")
            logger.error(f"Error response: {error_body}")
            if error.code == 404:
                raise InvokeServerUnavailableError(
                    f"Endpoint not found: {endpoint}. "
                    f"Please check your Azure AI Studio endpoint URL. "
                    f"For Cohere models, the endpoint should be like: https://[deployment-name].[region].models.ai.azure.com"
                )
            elif error.code == 401:
                raise InvokeAuthorizationError("Invalid API key or JWT token. Please check your credentials.")
            elif error.code == 400:
                raise InvokeBadRequestError(f"Bad request: {error_body}. Please check the request format.")
            else:
                raise InvokeError(f"HTTP Error {error.code}: {error_body}")
        except urllib.error.URLError as error:
            logger.error(f"Connection error: {error}")
            raise InvokeConnectionError(f"Failed to connect to endpoint: {endpoint}")

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
                return RerankResult(model=model, docs=[])
            endpoint = credentials.get("endpoint")
            api_key = credentials.get("jwt_token")
            if not endpoint or not api_key:
                raise ValueError("Azure endpoint and API key must be provided in credentials")
            # Pass model name if it looks like a specific model identifier
            model_name = model if model and model.lower() != "rerank" else None
            result = self._azure_rerank(query, docs, endpoint, api_key, model_name=model_name, top_n=top_n)
            logger.info(f"Azure rerank result: {result}")
            rerank_documents = []

            # Handle Azure AI Foundry rerank response format
            if isinstance(result, dict) and "results" in result:
                # Azure AI Foundry format: {"results": [{"index": 0, "relevance_score": 0.9}, ...]}
                for item in result["results"]:
                    idx = item.get("index", 0)
                    score = item.get("relevance_score", item.get("score", 0))
                    if idx < len(docs):
                        rerank_document = RerankDocument(index=idx, text=docs[idx], score=score)
                        if score_threshold is None or score >= score_threshold:
                            rerank_documents.append(rerank_document)
            elif isinstance(result, list):
                # Alternative format: list of scores
                for idx, score_item in enumerate(result):
                    if idx < len(docs):
                        if isinstance(score_item, dict):
                            score = score_item.get("score", score_item.get("relevance_score", 0))
                        else:
                            score = float(score_item)
                        rerank_document = RerankDocument(index=idx, text=docs[idx], score=score)
                        if score_threshold is None or score >= score_threshold:
                            rerank_documents.append(rerank_document)
            else:
                raise InvokeBadRequestError(f"Unexpected response format from Azure rerank API: {type(result)}")
            rerank_documents.sort(key=lambda x: x.score, reverse=True)
            if top_n:
                rerank_documents = rerank_documents[:top_n]
            return RerankResult(model=model, docs=rerank_documents)
        except Exception:
            logger.exception(f"Failed to invoke rerank model, model: {model}")
            raise

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
                score_threshold=0.8,
                top_n=2,
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
            InvokeConnectionError: [urllib.error.URLError],
            InvokeServerUnavailableError: [urllib.error.HTTPError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [
                InvokeBadRequestError,
                KeyError,
                ValueError,
                json.JSONDecodeError,
            ],
        }

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:  # noqa: ARG002
        """
        used to define customizable model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.RERANK,
            model_properties={},
            parameter_rules=[],
        )
        return entity
