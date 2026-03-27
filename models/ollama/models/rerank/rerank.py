import json
import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from dify_plugin import RerankModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
)
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

logger = logging.getLogger(__name__)


class OllamaRerankModel(RerankModel):
    """
    Model class for an Ollama rerank model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        query: str,
        documents: list[str],
        score_threshold: Optional[float] = None,
        top_n: Optional[int] = None,
        user: Optional[str] = None,
    ) -> RerankResult:
        """
        Invoke rerank model

        :param model: model name
        :param credentials: model credentials
        :param query: search query
        :param documents: docs for reranking
        :param score_threshold: score threshold
        :param top_n: top n documents to return
        :param user: unique user id
        :return: rerank result
        """
        if len(documents) == 0:
            return RerankResult(model=model, docs=[])

        headers = {"Content-Type": "application/json"}
        endpoint_url = credentials.get("base_url", "").rstrip("/")
        if not endpoint_url.endswith("/rerank"):
            endpoint_url = endpoint_url + "/api/rerank"

        payload = {
            "model": model,
            "query": query,
            "documents": documents,
        }

        # 添加可选参数
        if top_n is not None:
            payload["top_n"] = top_n

        try:
            response = requests.post(
                endpoint_url, 
                headers=headers, 
                data=json.dumps(payload), 
                timeout=(10, 300)
            )
            response.raise_for_status()
            response_data = response.json()

            rerank_documents = []
            results = response_data.get("results", [])
            
            # 如果指定了 top_n，只取前 top_n 个结果
            if top_n is not None:
                results = results[:top_n]

            for item in results:
                index = item["index"]
                # 兼容不同格式的响应
                if "document" in item:
                    text = item["document"]
                else:
                    text = documents[index] if index < len(documents) else ""
                score = item["relevance_score"]
                
                # 应用分数阈值过滤
                if score_threshold is None or score >= score_threshold:
                    rerank_document = RerankDocument(
                        index=index,
                        text=text,
                        score=score
                    )
                    rerank_documents.append(rerank_document)

            return RerankResult(model=model, docs=rerank_documents)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise InvokeAuthorizationError(str(e))
            elif e.response.status_code == 429:
                raise InvokeRateLimitError(str(e))
            elif e.response.status_code >= 500:
                raise InvokeServerUnavailableError(str(e))
            else:
                raise InvokeBadRequestError(str(e))
        except requests.exceptions.ConnectionError:
            raise InvokeConnectionError("Connection error occurred")
        except requests.exceptions.Timeout:
            raise InvokeConnectionError("Request timeout")
        except Exception as e:
            logger.error(f"Unexpected error in Ollama rerank: {str(e)}")
            raise InvokeError(f"Unexpected error: {str(e)}")

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
                documents=[
                    "Carson City is the capital city of the American state of Nevada.",
                    "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean.",
                ],
                score_threshold=0.0001,
            )
        except InvokeError as ex:
            raise CredentialsValidateFailedError(
                f"An error occurred during credentials validation: {ex.description}"
            )
        except requests.HTTPError as ex:
            raise CredentialsValidateFailedError(
                f"An error occurred during credentials validation: status code {ex.response.status_code}: {ex.response.text}"
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(
                f"An error occurred during credentials validation: {str(ex)}"
            )

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
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 512)
                ),
            },
        )
        return entity

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeAuthorizationError: [requests.exceptions.InvalidHeader],
            InvokeBadRequestError: [
                requests.exceptions.HTTPError,
                requests.exceptions.InvalidURL,
            ],
            InvokeRateLimitError: [requests.exceptions.RetryError],
            InvokeServerUnavailableError: [
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError,
            ],
            InvokeConnectionError: [
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ReadTimeout,
            ],
        }
