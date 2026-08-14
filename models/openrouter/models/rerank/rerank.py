from collections.abc import Mapping
from typing import NoReturn, Optional

import requests

from dify_plugin import RerankModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import AIModelEntity, FetchFrom, ModelPropertyKey, ModelType
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

from models._endpoint_utils import normalize_endpoint_url


class OpenRouterRerankModel(RerankModel):
    """Text rerank models served through OpenRouter's rerank API."""

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
        del user

        if not docs:
            return RerankResult(model=model, docs=[])

        api_key = credentials.get("api_key")
        if not api_key:
            raise InvokeAuthorizationError("API key is required.")

        payload: dict = {"model": model, "query": query, "documents": docs}
        if top_n is not None:
            payload["top_n"] = top_n

        endpoint_url = normalize_endpoint_url(credentials)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dify.ai/",
            "X-Title": "Dify",
        }

        try:
            response = requests.post(
                f"{endpoint_url}/rerank", headers=headers, json=payload, timeout=(10, 300)
            )
            response.raise_for_status()
            response_data = response.json()
        except requests.exceptions.HTTPError as ex:
            self._raise_http_error(ex)
        except requests.exceptions.Timeout as ex:
            raise InvokeConnectionError("OpenRouter rerank request timed out.") from ex
        except requests.exceptions.ConnectionError as ex:
            raise InvokeConnectionError("Unable to connect to OpenRouter.") from ex
        except requests.exceptions.JSONDecodeError as ex:
            raise InvokeServerUnavailableError(
                "OpenRouter returned an invalid JSON response."
            ) from ex
        except requests.exceptions.RequestException as ex:
            raise InvokeServerUnavailableError(str(ex)) from ex

        try:
            results = response_data["results"]
            reranked_docs = []
            for result in results:
                index = result["index"]
                score = result["relevance_score"]
                if not isinstance(index, int) or index < 0 or index >= len(docs):
                    raise ValueError(f"Invalid document index returned: {index!r}")
                if score_threshold is None or score >= score_threshold:
                    reranked_docs.append(RerankDocument(index=index, text=docs[index], score=score))
        except (KeyError, TypeError, ValueError) as ex:
            raise InvokeServerUnavailableError(
                f"OpenRouter returned an invalid rerank response: {ex}"
            ) from ex

        return RerankResult(model=model, docs=reranked_docs)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self._invoke(
                model=model,
                credentials=credentials,
                query="What is the capital of the United States?",
                docs=[
                    "Carson City is the capital of Nevada.",
                    "Washington, D.C. is the capital of the United States.",
                ],
                top_n=1,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def get_customizable_model_schema(self, model: str, credentials: Mapping) -> AIModelEntity:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.RERANK,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size") or 0)
            },
        )

    @staticmethod
    def _raise_http_error(error: requests.exceptions.HTTPError) -> NoReturn:
        response = error.response
        status_code = response.status_code if response is not None else None
        message = f"OpenRouter rerank request failed with status {status_code}."

        if status_code in (401, 403):
            raise InvokeAuthorizationError(message) from error
        if status_code == 429:
            raise InvokeRateLimitError(message) from error
        if status_code is not None and status_code >= 500:
            raise InvokeServerUnavailableError(message) from error
        raise InvokeBadRequestError(message) from error

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {}
