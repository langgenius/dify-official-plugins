import base64
import logging
import time
import os
import yaml
from typing import Optional
import dashscope
import numpy as np
import requests
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, MultiModalContent, MultiModalContentType, MultiModalEmbeddingResult, TextEmbeddingResult
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.text_embedding_model import TextEmbeddingModel
from models._common import _CommonTongyi, get_http_base_address
from ..constant import BURY_POINT_HEADER

vision_models = dict()

logger = logging.getLogger(__name__)

# Connection-level failures the DashScope SDK raises straight through (it does not
# wrap them): the remote end closing the connection surfaces as a requests
# ConnectionError, a stalled request as a requests Timeout. Both are transient.
_RETRYABLE_EXCEPTIONS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
# Backoff before each retry; its length is the number of retries.
_RETRY_BACKOFFS = (1, 3)


def _call_with_retry(call, payload):
    """Call the embedding endpoint, retrying transient connection failures.

    Once the retries are exhausted the original exception is re-raised unchanged so
    the provider error mapping can classify it as a connection error.
    """
    attempts = len(_RETRY_BACKOFFS) + 1
    for attempt, backoff in enumerate((*_RETRY_BACKOFFS, None), start=1):
        try:
            return call(payload)
        except _RETRYABLE_EXCEPTIONS as e:
            if backoff is None:
                raise
            logger.warning(
                "Connection error calling Tongyi embedding endpoint (attempt %d/%d), "
                "retrying in %ds: %s",
                attempt,
                attempts,
                backoff,
                e,
            )
            time.sleep(backoff)


class TongyiTextEmbeddingModel(_CommonTongyi, TextEmbeddingModel):
    """
    Model class for Tongyi text embedding model.
    """

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
        http_base_address = get_http_base_address(credentials)
        credentials_kwargs = self._to_credential_kwargs(credentials)
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)
        inputs = []
        indices = []
        used_tokens = 0
        for i, text in enumerate(texts):
            num_tokens = self._get_num_tokens_by_gpt2(text)
            if num_tokens >= context_size:
                cutoff = int(np.floor(len(text) * (context_size / num_tokens)))
                inputs.append(text[0:cutoff])
            else:
                inputs.append(text)
            indices += [i]
        batched_embeddings = []
        _iter = range(0, len(inputs), max_chunks)
        session = requests.Session()
        try:
            for i in _iter:
                (embeddings_batch, embedding_used_tokens) = self.embed_documents(
                    credentials_kwargs=credentials_kwargs,
                    model=model,
                    texts=inputs[i : i + max_chunks],
                    base_address=http_base_address,
                    session=session,
                )
                used_tokens += embedding_used_tokens
                batched_embeddings += embeddings_batch
            usage = self._calc_response_usage(
                model=model, credentials=credentials, tokens=used_tokens
            )
            return TextEmbeddingResult(embeddings=batched_embeddings, usage=usage, model=model)
        finally:
            session.close()

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return:
        """
        if len(texts) == 0:
            return []
        tokens = []
        for text in texts:
            tokens.append(self._get_num_tokens_by_gpt2(text))
        return tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        session = requests.Session()
        try:
            credentials_kwargs = self._to_credential_kwargs(credentials)
            http_base_address = get_http_base_address(credentials)
            self.embed_documents(
                credentials_kwargs=credentials_kwargs,
                model=model,
                texts=["ping"],
                base_address=http_base_address,
                session=session,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))
        finally:
            session.close()

    @staticmethod
    def embed_documents(
        credentials_kwargs: dict,
        model: str,
        texts: list[str],
        base_address: str,
        session: requests.Session,
    ) -> tuple[list[list[float]], int]:
        """Call out to Tongyi's embedding endpoint.

        Args:
            credentials_kwargs: The credentials to use for the call.
            model: The model to use for embedding.
            texts: The list of texts to embed.
            session: The requests session for this invocation.

        Returns:
            List of embeddings, one for each text, and tokens usage.
        """

        # If the model is vision model, it has different endpoint
        # transfer and call embed_multimodal_documents
        if TongyiTextEmbeddingModel._is_vision_model(model):
            documents = [MultiModalContent(content_type=MultiModalContentType.TEXT, content=text) for text in texts]
            return TongyiTextEmbeddingModel.embed_multimodal_documents(
                credentials_kwargs,
                model,
                documents,
                base_address,
                session,
            )

        embeddings = []
        embedding_used_tokens = 0
        
        def call_embedding_api(text):
            if model in ["multimodal-embedding-v1"]:
                return dashscope.MultiModalEmbedding.call(
                    api_key=credentials_kwargs["dashscope_api_key"],
                    model=model,
                    input=[{"text": text}],
                    base_address=base_address,
                    session=session,
                )
            else:
                return dashscope.TextEmbedding.call(
                    api_key=credentials_kwargs["dashscope_api_key"],
                    model=model,
                    input=text,
                    headers=BURY_POINT_HEADER,
                    text_type="document",
                    base_address=base_address,
                    session=session,
                )

        for text in texts:
            # First attempt
            response = _call_with_retry(call_embedding_api, text)
            # Handle rate limit error (429), which arrives as a response object
            if hasattr(response, 'status_code') and response.status_code == 429:
                logger.warning("Rate limit exceeded (429). Response: %s", response)
                time.sleep(10)
                # Retry once after sleeping
                response = _call_with_retry(call_embedding_api, text)
            
            # Process response
            if hasattr(response, 'output') and response.output and "embeddings" in response.output and response.output["embeddings"]:
                data = response.output["embeddings"][0]
                if "embedding" in data:
                    embeddings.append(data["embedding"])
                else:
                    raise ValueError(f"Embedding data is missing in the response: {response}")
            else:
                raise ValueError(f"Response output is missing or does not contain embeddings: {response}")
                
            if hasattr(response, 'usage') and response.usage and "total_tokens" in response.usage:
                embedding_used_tokens += response.usage["total_tokens"]
            else:
                if hasattr(response, 'usage') and response.usage:
                    if response.output["embeddings"][0]["type"] == "text":
                        embedding_used_tokens += response.usage["input_tokens"]
                    elif response.output["embeddings"][0]["type"] == "image":
                        embedding_used_tokens += response.usage["image_tokens"]
                else:
                    raise ValueError(f"Response usage is missing or does not contain total tokens: {response}")
        return ([list(map(float, e)) for e in embeddings], embedding_used_tokens)

    @staticmethod
    def _is_vision_model(model: str) -> bool:
        """
        Check whether there is a YAML configuration file in the current directory and whether it includes vision features.

        Args:
            model: The model name
        """
        if model not in vision_models:
            try:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                yaml_file_path = os.path.join(current_dir, f"{model}.yaml")

                if os.path.exists(yaml_file_path):
                    with open(yaml_file_path, 'r', encoding='utf-8') as f:
                        yaml_content = yaml.safe_load(f)

                    if (yaml_content and
                            'features' in yaml_content and
                            isinstance(yaml_content['features'], list) and
                            'vision' in yaml_content['features']):
                        vision_models[model] = True
            except Exception:
                pass
            vision_models[model] = False
        return vision_models[model]

    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
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

    def _invoke_multimodal(
        self, 
        model: str, 
        credentials: dict, 
        documents: list[MultiModalContent], 
        user: Optional[str] = None, 
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT) -> MultiModalEmbeddingResult:
        """
        Invoke multimodal text embedding model

        :param model: model name
        :param credentials: model credentials
        :param documents: documents to embed
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        http_base_address = get_http_base_address(credentials)
        credentials_kwargs = self._to_credential_kwargs(credentials)
        session = requests.Session()
        try:
            (embeddings_batch, embedding_used_tokens) = self.embed_multimodal_documents(
                credentials_kwargs=credentials_kwargs,
                model=model,
                documents=documents,
                base_address=http_base_address,
                session=session,
            )
            usage = self._calc_response_usage(
                model=model,
                credentials=credentials,
                tokens=embedding_used_tokens,
            )
            return MultiModalEmbeddingResult(
                model=model,
                embeddings=embeddings_batch,
                usage=usage,
            )
        finally:
            session.close()

    @staticmethod
    def embed_multimodal_documents(
        credentials_kwargs: dict,
        model: str,
        documents: list[MultiModalContent],
        base_address: str,
        session: requests.Session,
    ) -> tuple[list[list[float]], int]:
        """Call out to Tongyi's embedding endpoint.

        Args:
            credentials_kwargs: The credentials to use for the call.
            model: The model to use for embedding.
            documents: The list of documents to embed.
            session: The requests session for this invocation.

        Returns:
            List of embeddings, one for each text, and tokens usage.
        """
        def detect_image_format(base64_str: str) -> str:
            """
            Detect image format from base664 string

            :param base64_str: base64 string
            :return: image format
            """
            try:
                if "," in base64_str:
                    base64_str = base64_str.split(",", 1)[1]

                data = base64.b64decode(base64_str, validate=True)

                if data.startswith(b"\xFF\xD8\xFF"):
                    return "jpeg"
                elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                    return "png"
                elif data.startswith(b"BM"):
                    return "bmp"
                else:
                    return "unknown"
            except Exception:
                return "unknown"
        embeddings = []
        embedding_used_tokens = 0
        
        def call_embedding_api(input):
            return dashscope.MultiModalEmbedding.call(
                api_key=credentials_kwargs["dashscope_api_key"],
                model=model,
                input=[input],
                base_address=base_address,
                session=session,
            )

        for document in documents:
            # First attempt
            if document.content_type == MultiModalContentType.TEXT:
                input = {
                    "text": document.content
                }
            elif document.content_type == MultiModalContentType.IMAGE:
                image_format = detect_image_format(document.content)
                if image_format not in ["jpeg", "png", "bmp"]:
                    raise ValueError(f"Unsupported image format: {image_format}")
                input = {
                    "image": "data:image/" + image_format + ";base64," + document.content
                }
            else:
                raise ValueError(f"Unsupported content type: {document.content_type}")
            response = _call_with_retry(call_embedding_api, input)

            # Handle rate limit error (429), which arrives as a response object
            if hasattr(response, 'status_code') and response.status_code == 429:
                logger.warning("Rate limit exceeded (429). Response: %s", response)
                time.sleep(10)
                # Retry once after sleeping
                response = _call_with_retry(call_embedding_api, input)
            
            # Process response
            if hasattr(response, 'output') and response.output and "embeddings" in response.output and response.output["embeddings"]:
                data = response.output["embeddings"][0]
                if "embedding" in data:
                    embeddings.append(data["embedding"])
                else:
                    raise ValueError(f"Embedding data is missing in the response: {response}")
            else:
                raise ValueError(f"Response output is missing or does not contain embeddings: {response}")
                
            if hasattr(response, 'usage') and response.usage:
                if response.output["embeddings"][0]["type"] == "text":
                    embedding_used_tokens += response.usage["input_tokens"]
                elif response.output["embeddings"][0]["type"] == "image":
                    embedding_used_tokens += response.usage["image_tokens"]
            else:
                raise ValueError(f"Response usage is missing or does not contain total tokens: {response}")
                
        return ([list(map(float, e)) for e in embeddings], embedding_used_tokens)
