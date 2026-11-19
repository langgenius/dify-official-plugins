import math

from dify_plugin import RerankModel
from dify_plugin.entities.model.rerank import RerankDocument, RerankResult
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
    InvokeServerUnavailableError,
)

from models._api import TokenerAPIModel


class TokenerRerankModel(TokenerAPIModel, RerankModel):
    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self.invoke(model, credentials, "ping", ["ping"], top_n=1)
        except InvokeError as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

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
        if top_n is not None and (type(top_n) is not int or top_n < 1):
            raise InvokeBadRequestError("top_n must be a positive integer")
        if not docs:
            return RerankResult(model=model, docs=[])
        payload = {"model": model, "query": query, "documents": docs, "return_documents": False}
        if top_n is not None:
            payload["top_n"] = min(top_n, len(docs))
        response = self._post("rerank", credentials, payload)
        results = response["results"]
        if not isinstance(results, list):
            raise InvokeServerUnavailableError("Tokener.ai returned invalid rerank results")
        ranked = []
        seen = set()
        for result in results:
            index, score = result["index"], result["relevance_score"]
            if (
                type(index) is not int
                or not 0 <= index < len(docs)
                or index in seen
                or type(score) not in {int, float}
                or not math.isfinite(score)
            ):
                raise InvokeServerUnavailableError("Tokener.ai returned invalid rerank results")
            seen.add(index)
            if score_threshold is None or score >= score_threshold:
                ranked.append(RerankDocument(index=index, text=docs[index], score=score))
        ranked.sort(key=lambda doc: doc.score, reverse=True)
        return RerankResult(model=model, docs=ranked[:top_n])
