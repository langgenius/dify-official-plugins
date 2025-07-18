from typing import Optional
import httpx
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


class AihubmixRerankModel(RerankModel):
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
        if len(docs) == 0:
            return RerankResult(model=model, docs=[])
        base_url = credentials.get("base_url", "https://aihubmix.com/v1")
        base_url = base_url.removesuffix("/")
        try:
            response = httpx.post(
                base_url + "/rerank",
                json={"model": model, "query": query, "documents": docs, "top_n": top_n},
                headers={"Authorization": f"Bearer {credentials.get('api_key')}"},
            )
            response.raise_for_status()
            results = response.json()
            rerank_documents = []
            for result in results["results"]:
                if "document" in result and result["document"]:
                    rerank_document = RerankDocument(
                        index=result["index"], text=result["document"]["text"], score=result["relevance_score"]
                    )
                else:
                    doc_text = docs[result["index"]] if result["index"] < len(docs) else "default"
                    rerank_document = RerankDocument(
                        index=result["index"], text=doc_text, score=result["relevance_score"]
                    )
                if score_threshold is None or result["relevance_score"] >= score_threshold:
                    rerank_documents.append(rerank_document)
            return RerankResult(model=model, docs=rerank_documents)
        except httpx.HTTPStatusError as e:
            raise InvokeServerUnavailableError(str(e))

    def validate_credentials(self, model: str, credentials: dict) -> None:
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
