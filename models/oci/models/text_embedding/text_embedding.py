import base64
import json
import time
from typing import Any, NoReturn, Optional, Tuple

import oci

from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, TextEmbeddingResult
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.text_embedding_model import TextEmbeddingModel

from .call_api import patched_call_api
from oci.base_client import BaseClient

BaseClient.call_api = patched_call_api


class OCITextEmbeddingModel(TextEmbeddingModel):
    """
    OCI Generative AI Text Embedding Model
    - Extended to support multimodal image embeddings
    """

    # Conservative image batch size for OCI embedText(IMAGE)
    MAX_IMAGES_PER_REQUEST = 16

    # Maximum allowed image size (Dify: JPG/PNG/GIF, up to 2MB)
    MAX_IMAGE_BYTES = 2 * 1024 * 1024

    # Safety margin for truncation (tokenizer mismatch between GPT-2 estimate vs Cohere actual)
    TRUNCATION_SAFETY_MARGIN = 0.95

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

            pem_prefix = "-----BEGIN RSA PRIVATE KEY-----\n"
            pem_suffix = "\n-----END RSA PRIVATE KEY-----"
            key_string = credentials.get("key_content")

            key_b64: Optional[str] = None
            for part in key_string.split("-"):
                if len(part.strip()) > 64:
                    key_b64 = part.strip()

            if not key_b64:
                raise CredentialsValidateFailedError(
                    "failed to parse API key_content. Please provide valid PEM key content."
                )

            key_content = pem_prefix + "\n".join(key_b64.split(" ")) + pem_suffix

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

    # ---------------------------------------------------------
    # Common: Map OCI ServiceError to Dify's InvokeError
    # (NoReturn is appropriate as it always raises an exception)
    # ---------------------------------------------------------
    def _raise_invoke_error_from_oci(self, e: Exception) -> NoReturn:
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
    # Create the client (instantiate once inside invoke and reuse it).
    # ---------------------------------------------------------
    def _create_client(self, credentials: dict) -> oci.generative_ai_inference.GenerativeAiInferenceClient:
        oci_credentials = self._get_oci_credentials(credentials)
        return oci.generative_ai_inference.GenerativeAiInferenceClient(**oci_credentials)

    # ---------------------------------------------------------
    # Dify input_type -> OCI inputType
    # ---------------------------------------------------------
    def _map_embedding_input_type_to_oci(self, input_type: EmbeddingInputType) -> Optional[str]:
        """
        Cohere embed models often benefit from:
        - QUERY    -> SEARCH_QUERY
        - DOCUMENT -> SEARCH_DOCUMENT
        """
        if input_type == EmbeddingInputType.QUERY:
            return "SEARCH_QUERY"
        return "SEARCH_DOCUMENT"

    # ---------------------------------------------------------
    # OCI embedText response parser (explicit JSON / schema validation)
    # ---------------------------------------------------------
    def _parse_embed_response(
        self,
        response_text: Any,
        expected_count: Optional[int] = None,
    ) -> Tuple[list[list[float]], int]:
        """
        Parse embedText API response safely.
        Expected schema:
          {
            "embeddings": [...],
            "usage": {"totalTokens": N}
          }

        expected_count: if provided, validate len(embeddings) matches the request inputs.
        """
        # bytes -> str safety
        if isinstance(response_text, (bytes, bytearray)):
            try:
                response_text = response_text.decode("utf-8", errors="replace")
            except Exception:
                response_text = str(response_text)

        try:
            json_response = json.loads(response_text)
            embeddings = json_response["embeddings"]
            embedding_used_tokens = int(json_response["usage"]["totalTokens"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            preview = response_text[:300] if isinstance(response_text, str) else str(response_text)[:300]
            raise InvokeBadRequestError(f"invalid API response: {e}. preview={preview}") from e

        # schema sanity
        if not isinstance(embeddings, list):
            preview = str(json_response)[:300]
            raise InvokeBadRequestError(f"invalid API response: embeddings is not a list. preview={preview}")

        if expected_count is not None and len(embeddings) != expected_count:
            raise InvokeBadRequestError(
                f"invalid API response: embeddings count mismatch (expected {expected_count}, got {len(embeddings)})"
            )

        return embeddings, embedding_used_tokens

    # ---------------------------------------------------------
    # Text embedding
    # ---------------------------------------------------------
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        self.started_at = time.perf_counter()

        if not texts:
            usage = self._calc_response_usage(model=model, credentials=credentials, tokens=0)
            return TextEmbeddingResult(embeddings=[], usage=usage, model=model)

        # Create the client once here and reuse it.
        try:
            client = self._create_client(credentials)
        except Exception as e:
            self._raise_invoke_error_from_oci(e)

        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)

        # Clamp max_chunks to prevent crashes even if it is misconfigured.
        if not isinstance(max_chunks, int) or max_chunks <= 0:
            max_chunks = 1

        inputs: list[str] = []
        used_tokens = 0

        # truncate by context size (with safety margin)
        for text in texts:
            if context_size <= 0:
                inputs.append(text)
                continue

            num_tokens = self._get_num_tokens_by_gpt2(text)

            if num_tokens == 0:
                inputs.append(text)
                continue

            if num_tokens > context_size:
                ratio = (context_size / num_tokens) * self.TRUNCATION_SAFETY_MARGIN
                cutoff = max(0, int(len(text) * ratio))
                inputs.append(text[:cutoff])
            else:
                inputs.append(text)

        batched_embeddings: list[list[float]] = []
        oci_input_type = self._map_embedding_input_type_to_oci(input_type)

        for i in range(0, len(inputs), max_chunks):
            chunk = inputs[i : i + max_chunks]
            embeddings_batch, embedding_used_tokens = self._embedding_invoke(
                client=client,
                model=model,
                credentials=credentials,
                texts=chunk,
                oci_input_type=oci_input_type,
            )
            used_tokens += embedding_used_tokens
            batched_embeddings += embeddings_batch

        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=used_tokens)
        return TextEmbeddingResult(embeddings=batched_embeddings, usage=usage, model=model)

    # =========================================================
    # Image embedding (batch support)
    # =========================================================
    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        files: list[Any],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        self.started_at = time.perf_counter()

        if not files:
            usage = self._calc_response_usage(model=model, credentials=credentials, tokens=0)
            return TextEmbeddingResult(embeddings=[], usage=usage, model=model)

        # Create the client once here and reuse it.
        try:
            client = self._create_client(credentials)
        except Exception as e:
            self._raise_invoke_error_from_oci(e)

        image_data_uris: list[str] = []
        for f in files:
            image_base64 = self._extract_base64_from_multimodal_content(f)
            mime_type = self._validate_image_base64(image_base64, f)
            image_data_uris.append(self._to_base64_data_uri(image_base64=image_base64, mime_type=mime_type))

        used_tokens = 0
        embeddings: list[list[float]] = []

        for i in range(0, len(image_data_uris), self.MAX_IMAGES_PER_REQUEST):
            batch = image_data_uris[i : i + self.MAX_IMAGES_PER_REQUEST]
            emb_batch, tok = self._embedding_invoke_image(
                client=client,
                model=model,
                credentials=credentials,
                image_data_uris=batch,
            )
            used_tokens += tok
            embeddings += emb_batch

        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=used_tokens)
        return TextEmbeddingResult(embeddings=embeddings, usage=usage, model=model)

    # ---------------------------------------------------------
    # MultiModalContent compatibility helper
    # ---------------------------------------------------------
    def _as_dict_if_possible(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
            try:
                return obj.model_dump()
            except Exception as e:
                raise InvokeBadRequestError("failed to convert multimodal content to dict") from e
        return obj

    def _extract_base64_from_multimodal_content(self, content: Any) -> str:
        c = self._as_dict_if_possible(content)

        b64: Optional[str] = None
        if isinstance(c, dict):
            b64 = c.get("data") or c.get("base64") or c.get("content")
        else:
            b64 = getattr(c, "data", None) or getattr(c, "base64", None) or getattr(c, "content", None)

        if not b64 or not isinstance(b64, str):
            raise InvokeBadRequestError(
                "multimodal file does not contain base64 data in 'data' (or 'base64'/'content') field"
            )

        if b64.startswith("data:") and "base64," in b64:
            b64 = b64.split("base64,", 1)[-1]

        return b64

    def _extract_content_type_from_multimodal_content(self, content: Any) -> Optional[str]:
        c = self._as_dict_if_possible(content)

        if isinstance(c, dict):
            ct = c.get("content_type") or c.get("mime_type") or c.get("type")
        else:
            ct = getattr(c, "content_type", None) or getattr(c, "mime_type", None) or getattr(c, "type", None)

        if isinstance(ct, str):
            return ct
        return None

    def _detect_image_mime(self, raw: bytes) -> str:
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if raw.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
            return "image/gif"
        raise InvokeBadRequestError("unsupported image format (allowed: JPEG/PNG/GIF)")

    def _to_base64_data_uri(self, image_base64: str, mime_type: str) -> str:
        return f"data:{mime_type};base64,{image_base64}"

    def _validate_image_base64(self, image_base64: str, original_content: Any) -> str:
        content_type = self._extract_content_type_from_multimodal_content(original_content)

        allowed_mimes = {"image/jpeg", "image/jpg", "image/png", "image/gif"}

        if content_type:
            ct_lower = content_type.lower()
            if ct_lower != "image" and ct_lower not in allowed_mimes:
                raise InvokeBadRequestError(f"unsupported image content_type: {content_type}")

        max_bytes = self.MAX_IMAGE_BYTES
        try:
            raw = base64.b64decode(image_base64, validate=True)
        except Exception as e:
            raise InvokeBadRequestError("invalid base64 for image input") from e

        if len(raw) > max_bytes:
            raise InvokeBadRequestError(f"image size exceeds limit: {len(raw)} bytes > {max_bytes} bytes")

        if content_type:
            ct_lower = content_type.lower()
            if ct_lower in {"image/jpeg", "image/jpg"}:
                return "image/jpeg"
            if ct_lower == "image/png":
                return "image/png"
            if ct_lower == "image/gif":
                return "image/gif"

        return self._detect_image_mime(raw)

    # ---------------------------------------------------------
    # Usage counting related logic
    # ---------------------------------------------------------
    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        return [self._get_num_tokens_by_gpt2(text) for text in texts]

    def get_num_characters(self, model: str, credentials: dict, texts: list[str]) -> int:
        return sum(len(text) for text in texts)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Called when Dify validates credentials.
        Instantiate the client only once and perform a lightweight request as a connectivity check.
        """
        try:
            client = self._create_client(credentials)
            self._embedding_invoke(
                client=client,
                model=model,
                credentials=credentials,
                texts=["ping"],
                oci_input_type=None,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    # ---------------------------------------------------------
    # Text embedding call (reuse client + optional inputType)
    # ---------------------------------------------------------
    def _embedding_invoke(
        self,
        client: oci.generative_ai_inference.GenerativeAiInferenceClient,
        model: str,
        credentials: dict,
        texts: list[str],
        oci_input_type: Optional[str] = None,
    ) -> Tuple[list[list[float]], int]:
        try:
            kwargs = {
                "compartment_id": credentials.get("compartment_ocid"),
                "serving_mode": oci.generative_ai_inference.models.OnDemandServingMode(
                    serving_type="ON_DEMAND",
                    model_id=model,
                ),
                "inputs": texts,
            }
            if oci_input_type:
                kwargs["input_type"] = oci_input_type

            try:
                embed_text_details = oci.generative_ai_inference.models.EmbedTextDetails(**kwargs)
            except TypeError:
                # SDK version mismatch: input_type parameter not supported (or different name)
                kwargs.pop("input_type", None)
                embed_text_details = oci.generative_ai_inference.models.EmbedTextDetails(**kwargs)

            body = client.base_client.sanitize_for_serialization(embed_text_details)
            body = json.dumps(body)

            response = client.base_client.call_api(
                resource_path="/actions/embedText",
                method="POST",
                operation_name="embedText",
                header_params={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                },
                body=body,
            )

            # Verify that the chunk count matches the number of embeddings.
            return self._parse_embed_response(response.data.text, expected_count=len(texts))

        except Exception as e:
            self._raise_invoke_error_from_oci(e)

    # ---------------------------------------------------------
    # Image embedding call (reuse client + fallback + batch support)
    # ---------------------------------------------------------
    def _embedding_invoke_image(
        self,
        client: oci.generative_ai_inference.GenerativeAiInferenceClient,
        model: str,
        credentials: dict,
        image_data_uris: list[str],
    ) -> Tuple[list[list[float]], int]:
        try:
            try:
                embed_text_details = oci.generative_ai_inference.models.EmbedTextDetails(
                    compartment_id=credentials.get("compartment_ocid"),
                    serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
                        serving_type="ON_DEMAND",
                        model_id=model,
                    ),
                    inputs=image_data_uris,
                    input_type="IMAGE",
                )
                body_obj = client.base_client.sanitize_for_serialization(embed_text_details)

            except TypeError:
                # SDK version mismatch: input_type parameter not supported
                body_obj = {
                    "compartmentId": credentials.get("compartment_ocid"),
                    "servingMode": {
                        "servingType": "ON_DEMAND",
                        "modelId": model,
                    },
                    "inputs": image_data_uris,
                    "inputType": "IMAGE",
                }

            body = json.dumps(body_obj)

            response = client.base_client.call_api(
                resource_path="/actions/embedText",
                method="POST",
                operation_name="embedText",
                header_params={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                },
                body=body,
            )

            # Validate consistency between the batch size and the number of embeddings.
            return self._parse_embed_response(response.data.text, expected_count=len(image_data_uris))

        except Exception as e:
            self._raise_invoke_error_from_oci(e)

    # ---------------------------------------------------------
    # Usage calculation
    # ---------------------------------------------------------
    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens,
        )

        started_at = getattr(self, "started_at", None)
        if started_at is None:
            started_at = time.perf_counter()

        usage = EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - started_at,
        )
        return usage

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [InvokeBadRequestError, KeyError],
        }

