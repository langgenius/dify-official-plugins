import json
import logging
from typing import Any, NoReturn, Optional

import oci
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

from utils.oci_private_key import normalize_private_key

logger = logging.getLogger(__name__)


class OCIRerankModel(RerankModel):
    """
    OCI Generative AI rerank model (Cohere Rerank served on-demand through the
    ``rerankText`` action of the Generative AI Inference API).
    """

    # rerankText rejects a request when len(documents) * maxChunksPerDocument > 10000.
    # With the service default of 10 chunks per document that caps a single call at
    # 1000 documents, so larger inputs are reranked in batches and merged by score.
    MAX_DOCUMENTS_PER_REQUEST = 1000

    # ---------------------------------------------------------
    # Credentials -> OCI client kwargs (same contract as llm / text_embedding)
    # ---------------------------------------------------------
    def _get_oci_credentials(self, credentials: dict) -> dict:
        auth_method = credentials.get("authentication_method")

        if auth_method == "instance_principal_authentication":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            return {"config": {}, "signer": signer}

        if auth_method == "api_key_authentication":
            required = [
                "key_content",
                "tenancy_ocid",
                "user_ocid",
                "fingerprint",
                "default_region",
                "compartment_ocid",
            ]
            for k in required:
                if k not in credentials:
                    raise CredentialsValidateFailedError(f"need to set {k} in credentials")

            key_content = normalize_private_key(credentials.get("key_content"))

            config = {
                "tenancy": credentials.get("tenancy_ocid"),
                "user": credentials.get("user_ocid"),
                "fingerprint": credentials.get("fingerprint"),
                "key_content": key_content,
                "region": credentials.get("default_region"),
                "pass_phrase": None,
            }

            oci.config.validate_config(config)
            return {"config": config}

        raise CredentialsValidateFailedError(f"unsupported authentication_method: {auth_method}")

    def _create_client(self, credentials: dict) -> oci.generative_ai_inference.GenerativeAiInferenceClient:
        oci_credentials = self._get_oci_credentials(credentials)
        return oci.generative_ai_inference.GenerativeAiInferenceClient(**oci_credentials)

    # ---------------------------------------------------------
    # Map OCI ServiceError to Dify's InvokeError
    # ---------------------------------------------------------
    def _raise_invoke_error_from_oci(self, e: Exception) -> NoReturn:
        if isinstance(e, InvokeError):
            raise e

        if isinstance(e, oci.exceptions.ServiceError):
            status = getattr(e, "status", None)
            msg = str(e)

            if status in (401, 403):
                raise InvokeAuthorizationError(msg) from e
            if status == 429:
                raise InvokeRateLimitError(msg) from e
            if status is not None and status >= 500:
                raise InvokeServerUnavailableError(msg) from e

            raise InvokeBadRequestError(msg) from e

        raise InvokeConnectionError(str(e)) from e

    # ---------------------------------------------------------
    # Rerank
    # ---------------------------------------------------------
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
        if not docs:
            return RerankResult(model=model, docs=[])

        try:
            client = self._create_client(credentials)
        except Exception as e:
            self._raise_invoke_error_from_oci(e)

        ranked: list[RerankDocument] = []
        for offset in range(0, len(docs), self.MAX_DOCUMENTS_PER_REQUEST):
            batch = docs[offset : offset + self.MAX_DOCUMENTS_PER_REQUEST]
            ranked.extend(
                self._rerank_invoke(
                    client=client,
                    model=model,
                    credentials=credentials,
                    query=query,
                    docs=batch,
                    offset=offset,
                    top_n=top_n,
                )
            )

        # Relevance scores are absolute per (query, document) pair, so batches can be
        # merged by score. Sort descending and apply top_n / threshold on the merged list.
        ranked.sort(key=lambda d: d.score, reverse=True)

        if score_threshold is not None:
            ranked = [d for d in ranked if d.score >= score_threshold]
        if top_n is not None:
            ranked = ranked[:top_n]

        return RerankResult(model=model, docs=ranked)

    def _rerank_invoke(
        self,
        client: oci.generative_ai_inference.GenerativeAiInferenceClient,
        model: str,
        credentials: dict,
        query: str,
        docs: list[str],
        offset: int = 0,
        top_n: Optional[int] = None,
    ) -> list[RerankDocument]:
        """
        Single rerankText call. Returned indexes are shifted by ``offset`` so that they
        refer to the caller's full document list.

        The request is serialised to JSON and sent through ``base_client.call_api`` (the
        same way ``llm.py`` and ``text_embedding.py`` call ``chat`` / ``embedText``): the
        plugin patches ``BaseClient.call_api`` globally, which breaks the SDK's typed
        ``rerank_text`` wrapper.
        """
        try:
            kwargs = {
                "compartment_id": credentials.get("compartment_ocid"),
                "serving_mode": oci.generative_ai_inference.models.OnDemandServingMode(
                    serving_type="ON_DEMAND",
                    model_id=model,
                ),
                "input": query,
                "documents": docs,
                # The texts are already available locally; don't pay for echoing them back.
                "is_echo": False,
            }
            if top_n is not None:
                kwargs["top_n"] = max(1, min(top_n, len(docs)))

            details = oci.generative_ai_inference.models.RerankTextDetails(**kwargs)
            body = json.dumps(client.base_client.sanitize_for_serialization(details))

            response = client.base_client.call_api(
                resource_path="/actions/rerankText",
                method="POST",
                operation_name="rerankText",
                header_params={
                    # Same accept header as llm.py / text_embedding.py: with the patched
                    # call_api, a plain application/json accept yields no response body.
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                },
                body=body,
            )

            return self._parse_rerank_response(response.data.text, docs=docs, offset=offset)

        except Exception as e:
            self._raise_invoke_error_from_oci(e)

    def _parse_rerank_response(self, response_text: Any, docs: list[str], offset: int = 0) -> list[RerankDocument]:
        """
        Parse a RerankTextResult payload: {"documentRanks": [{"index": 0, "relevanceScore": 0.9, ...}], ...}
        """
        if isinstance(response_text, (bytes, bytearray)):
            response_text = response_text.decode("utf-8", errors="replace")

        try:
            json_response = json.loads(response_text)
            ranks = json_response["documentRanks"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            preview = str(response_text)[:300]
            raise InvokeBadRequestError(f"invalid API response: {e}. preview={preview}") from e

        if ranks is None:
            return []
        if not isinstance(ranks, list):
            raise InvokeBadRequestError("invalid API response: documentRanks is not a list")

        results: list[RerankDocument] = []
        for rank in ranks:
            try:
                index = int(rank["index"])
                score = float(rank["relevanceScore"])
            except (KeyError, TypeError, ValueError) as e:
                raise InvokeBadRequestError(f"invalid API response: malformed document rank {rank!r}") from e
            if index < 0 or index >= len(docs):
                raise InvokeBadRequestError(
                    f"invalid API response: document index {index} out of range (0..{len(docs) - 1})"
                )
            results.append(RerankDocument(index=offset + index, text=docs[index], score=score))
        return results

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials with a minimal rerank request.

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self.invoke(
                model=model,
                credentials=credentials,
                query="What is the capital of the United States?",
                docs=[
                    "Carson City is the capital city of the American state of Nevada.",
                    "Washington, D.C. is the capital of the United States.",
                ],
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error. Errors raised by ``_invoke`` are already
        normalised by ``_raise_invoke_error_from_oci``; this mapping lets the SDK pass
        them through unchanged.
        """
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [InvokeBadRequestError],
        }
