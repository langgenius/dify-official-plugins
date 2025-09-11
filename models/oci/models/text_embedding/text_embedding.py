import base64
import copy
import json
import time
from typing import Optional
import numpy as np
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
    Model class for Cohere text embedding model.
    """

    def _get_oci_credentials(self, credentials: dict) -> dict:
        if credentials.get("authentication_method") == "instance_principal_authentication":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            oci_credentials = {"config": {}, "signer": signer}
        elif credentials.get("authentication_method") == "api_key_authentication":
            if "key_content" not in credentials:
                raise CredentialsValidateFailedError("need to set key_content in credentials ")
            if "tenancy_ocid" not in credentials:
                raise CredentialsValidateFailedError("need to set tenancy_ocid in credentials ")
            if "user_ocid" not in credentials:
                raise CredentialsValidateFailedError("need to set user_ocid in credentials ")
            if "fingerprint" not in credentials:
                raise CredentialsValidateFailedError("need to set fingerprint in credentials ")
            if "default_region" not in credentials:
                raise CredentialsValidateFailedError("need to set default_region in credentials ")
            if "compartment_ocid" not in credentials:
                raise CredentialsValidateFailedError("need to set compartment_ocid in credentials ")

            pem_prefix = '-----BEGIN RSA PRIVATE KEY-----\n'
            pem_suffix = '\n-----END RSA PRIVATE KEY-----'
            key_string = credentials.get("key_content")
            for part in key_string.split("-"):
                if len(part.strip()) > 64:
                    key_b64 = part.strip()
            key_content = pem_prefix + "\n".join(key_b64.split(" "))+ pem_suffix
            
            config = {
                "tenancy": credentials.get("tenancy_ocid"),
                "user": credentials.get("user_ocid"),
                "fingerprint": credentials.get("fingerprint"),
                "key_content": key_content,
                "region": credentials.get("default_region"),
                "pass_phrase": None
            }                
            
            oci.config.validate_config(config)
            oci_credentials = {"config": config}
        return oci_credentials

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke text embedding model

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)
        inputs = []
        indices = []
        used_tokens = 0
        for i, text in enumerate(texts):
            num_tokens = self._get_num_tokens_by_gpt2(text)
            if num_tokens >= context_size:
                cutoff = int(len(text) * np.floor(context_size / num_tokens))
                inputs.append(text[0:cutoff])
            else:
                inputs.append(text)
            indices += [i]
        batched_embeddings = []
        _iter = range(0, len(inputs), max_chunks)
        for i in _iter:
            (embeddings_batch, embedding_used_tokens) = self._embedding_invoke(
                model=model, credentials=credentials, texts=inputs[i : i + max_chunks]
            )
            used_tokens += embedding_used_tokens
            batched_embeddings += embeddings_batch
        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=used_tokens)
        return TextEmbeddingResult(embeddings=batched_embeddings, usage=usage, model=model)

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return:
        """
        num_tokens = []
        for text in texts:
            num_tokens.append(self._get_num_tokens_by_gpt2(text))
        return num_tokens

    def get_num_characters(self, model: str, credentials: dict, texts: list[str]) -> int:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return:
        """
        characters = 0
        for text in texts:
            characters += len(text)
        return characters

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._embedding_invoke(model=model, credentials=credentials, texts=["ping"])
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _embedding_invoke(self, model: str, credentials: dict, texts: list[str]) -> tuple[list[list[float]], int]:
        """
        Invoke embedding model

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return: embeddings and used tokens
        """
        oci_credentials = self._get_oci_credentials(credentials)
        client = oci.generative_ai_inference.GenerativeAiInferenceClient(**oci_credentials)

        embed_text_details = oci.generative_ai_inference.models.EmbedTextDetails(
            compartment_id=credentials.get("compartment_ocid"),
            serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
                serving_type="ON_DEMAND",
                model_id=model,
            ),
            # truncate = "NONE",
            inputs=texts,
        )
        body = client.base_client.sanitize_for_serialization(embed_text_details)
        body = json.dumps(body)

        response = client.base_client.call_api(
            resource_path="/actions/embedText",
            method="POST",
            operation_name="embedText",
            header_params={
                "accept": "application/json, text/event-stream",
                "content-type": "application/json"
            },
            body=body
            )
        # response = client.embed_text(embed_text_details)
        json_response = json.loads(response.data.text)
        embeddings = json_response["embeddings"]
        embedding_used_tokens = json_response["usage"]["totalTokens"]
        #embedding_characters = len(texts)
        return (embeddings, embedding_used_tokens)
        #return (embeddings, self.get_num_characters(model=model, credentials=credentials, texts=texts))

    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: input tokens
        :return: usage
        """
        input_price_info = self.get_price(
            model=model, credentials=credentials, price_type=PriceType.INPUT, tokens=tokens
        )
        usage = EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - self.started_at,
        )
        return usage

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
            InvokeBadRequestError: [KeyError],
        }
