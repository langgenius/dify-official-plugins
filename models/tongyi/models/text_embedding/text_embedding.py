import base64
import logging
import time
import os
import yaml
from typing import Optional
import dashscope
import numpy as np
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, MultiModalContent, MultiModalContentType, MultiModalEmbeddingResult, TextEmbeddingResult
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.text_embedding_model import TextEmbeddingModel
from models._common import _CommonTongyi
from ..constant import BURY_POINT_HEADER
from ..endpoint_helper import get_base_address

logger = logging.getLogger(__name__)

vision_models = dict()

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
        for i in _iter:
            (embeddings_batch, embedding_used_tokens) = self.embed_documents(
                credentials_kwargs=credentials_kwargs, model=model, texts=inputs[i: i + max_chunks],
                credentials=credentials
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
        try:
            credentials_kwargs = self._to_credential_kwargs(credentials)
            self.embed_documents(credentials_kwargs=credentials_kwargs, model=model, texts=["ping"], credentials=credentials)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    @staticmethod
    def embed_documents(credentials_kwargs: dict, model: str, texts: list[str], credentials: dict = None) -> tuple[list[list[float]], int]:
        """Call out to Tongyi's embedding endpoint.

        Args:
            credentials_kwargs: The credentials to use for the call.
            model: The model to use for embedding.
            texts: The list of texts to embed.
            credentials: Full credentials dict for endpoint configuration.

        Returns:
            List of embeddings, one for each text, and tokens usage.
        """

        # If the model is vision model, it has different endpoint
        # transfer and call embed_multimodal_documents
        if TongyiTextEmbeddingModel._is_vision_model(model):
            documents = [MultiModalContent(content_type=MultiModalContentType.TEXT, content=text) for text in texts]
            return TongyiTextEmbeddingModel.embed_multimodal_documents(credentials_kwargs, model, documents, credentials)

        embeddings = []
        embedding_used_tokens = 0

        if credentials is None:
            # For backward compatibility, use global setting
            credentials = {}

        # Get base address for this request
        base_address = get_base_address(credentials)

        def call_embedding_api(text):
            try:
                if model in ["multimodal-embedding-v1"]:
                    return dashscope.MultiModalEmbedding.call(
                        api_key=credentials_kwargs["dashscope_api_key"],
                        model=model,
                        input=[{"text": text}],
                        base_address=base_address,
                    )
                else:
                    return dashscope.TextEmbedding.call(
                        api_key=credentials_kwargs["dashscope_api_key"],
                        model=model,
                        input=text,
                        headers=BURY_POINT_HEADER,
                        text_type="document",
                        base_address=base_address,
                    )
            except Exception as e:
                # Return the exception to be handled by the caller
                return e

        for text in texts:
            # First attempt
            response = call_embedding_api(text)
            # Handle rate limit error (429)
            # Check if response is an exception with rate limit info
            if hasattr(response, 'status_code') and response.status_code == 429:
                logger.warning(f"Rate limit exceeded (429). Response: {response}")
                time.sleep(10)
                # Retry once after sleeping
                response = call_embedding_api(text)

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
        credentials_kwargs = self._to_credential_kwargs(credentials)
        (embeddings_batch, embedding_used_tokens) = self.embed_multimodal_documents(
            credentials_kwargs=credentials_kwargs, model=model, documents=documents, credentials=credentials
        )
        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=embedding_used_tokens)
        return MultiModalEmbeddingResult(
            model=model,
            embeddings=embeddings_batch,
            usage=usage,
        )

    @staticmethod
    def embed_multimodal_documents(credentials_kwargs: dict, model: str, documents: list[MultiModalContent], credentials: dict = None) -> tuple[list[list[float]], int]:
        """Call out to Tongyi's embedding endpoint.

        Args:
            credentials_kwargs: The credentials to use for the call.
            model: The model to use for embedding.
            documents: The list of documents to embed.
            credentials: Full credentials dict for endpoint configuration.

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

        if credentials is None:
            # For backward compatibility, use global setting
            credentials = {}

        # Get base address for this request
        base_address = get_base_address(credentials)

        def call_embedding_api(input):
            try:
                return dashscope.MultiModalEmbedding.call(
                    api_key=credentials_kwargs["dashscope_api_key"],
                    model=model,
                    input=[input],
                    base_address=base_address,
                )
            except Exception as e:
                # Return the exception to be handled by the caller
                return e

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
            response = call_embedding_api(input)

            # Handle rate limit error (429)
            # Check if response is an exception with rate limit info
            if hasattr(response, 'status_code') and response.status_code == 429:
                logger.warning(f"Rate limit exceeded (429). Response: {response}")
                time.sleep(10)
                # Retry once after sleeping
                response = call_embedding_api(input)

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
