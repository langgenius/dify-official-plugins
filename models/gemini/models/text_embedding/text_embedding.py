"""
FutureWarning:
All support for the `google.generativeai` package has ended. It will no longer be receiving
updates or bug fixes. Please switch to the `google.genai` package as soon as possible.
"""

import base64
import binascii
import logging
import re
import time
import numpy as np
from typing import Optional, Union
from collections.abc import Mapping

from google import genai
from google.genai import types
from google.genai.types import EmbedContentConfig
from google.generativeai.embedding import to_task_type

from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    MultiModalContent,
    MultiModalContentType,
    MultiModalEmbeddingResult,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError

from ..common_gemini import _CommonGemini

logger = logging.getLogger(__name__)

# Embedding and number of tokens used
EmbeddingTokenPair = tuple[list[float], Optional[int]]


class GeminiTextEmbeddingModel(_CommonGemini, TextEmbeddingModel):
    """
    Model class for Gemini text embedding model.
    """

    # ---- Gemini Embedding 2 modality-specific limits ----
    # https://ai.google.dev/gemini-api/docs/embeddings#modality-limits
    # Image: max 6 per request, PNG/JPEG only
    MAX_IMAGES_PER_REQUEST = 6
    SUPPORTED_IMAGE_FORMATS = {"image/jpeg", "image/png"}
    # Audio: max 80 seconds, MP3/WAV (not yet supported)
    # Video: max 128 seconds, MP4/MOV, codecs: H264/H265/AV1/VP9 (not yet supported)
    # Document (PDF): max 6 pages (not yet supported)

    # Fallback token estimate for image content when API does not return statistics.
    # Google's documentation indicates images are processed at ~258 tokens on average.
    IMAGE_TOKEN_ESTIMATE = 258

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
        :return: embeddings result
        """
        client = genai.Client(api_key=credentials["google_api_key"])

        # get model properties
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)

        # splitted texts in case the chunks are bigger than the context size
        splitted_texts = [
            self._split_texts_to_fit_model_specs(client, model, [text], context_size)
            for text in texts
        ]

        # list batched texts of size <= max_chunks containing (text index, text)
        batched_texts: list[list[tuple[int, str]]] = [[]]
        for i, splitted_text in enumerate(splitted_texts):
            for text, _ in splitted_text:
                if len(batched_texts[-1]) >= max_chunks:
                    batched_texts.append([])
                batched_texts[-1].append((i, text))

        # list of embeddings following the same arrangement as splitted_texts
        splitted_embeddings: list[list[EmbeddingTokenPair]] = []
        for batch in batched_texts:
            embeddings_batch = self._embedding_invoke(
                model=model,
                client=client,
                texts=[text for _, text in batch],
                input_type=input_type,
            )
            for i, (j, _) in enumerate(batch):
                if j >= len(splitted_embeddings):
                    splitted_embeddings.append([])
                splitted_embeddings[j].append(embeddings_batch[i])

        # merge embeddings by averaging them
        merged_embeddings: list[list[float]] = []
        used_tokens = 0
        for i, embeddings in enumerate(splitted_embeddings):
            embeddings, num_tokens = zip(*embeddings)
            if len(embeddings) == 1:
                embedding = embeddings[0]
            else:
                average = np.average(embeddings, axis=0, weights=num_tokens)
                embedding = (average / np.linalg.norm(average)).tolist()
                if np.isnan(embedding).any():
                    raise ValueError("Normalized embedding is nan please try again")
            merged_embeddings.append(embedding)
            # sum up the number of tokens used if available or the count estimation from the text chunking
            used_tokens += sum(
                [
                    used_token or chunk_size
                    for used_token, [_, chunk_size] in zip(
                        num_tokens, splitted_texts[i]
                    )
                ]
            )

        # calc usage
        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=used_tokens
        )

        return TextEmbeddingResult(
            embeddings=merged_embeddings, usage=usage, model=model
        )

    def _split_texts_to_fit_model_specs(
        self, client: genai.Client, model: str, texts: list[str], context_size: int
    ) -> list[tuple[str, int]]:
        """
        Split text to fit model specs based on the model context size

        :param client: model client
        :param model: model name
        :param text: text to truncate
        :return: list of tuples (text, estimated chunk size)
        """
        splitted_text = []
        for text in texts:
            num_tokens = self._count_tokens(client, model, text)
            if num_tokens >= context_size:
                cutoff = context_size
                # split text by the closest punctuation mark or then by comma or space
                for pattern in [r"[.!?]", r",", r"\s"]:
                    match = re.search(pattern, text[context_size:])
                    if match:
                        cutoff = context_size + match.start() + 1
                        break
                splitted_text.extend(
                    self._split_texts_to_fit_model_specs(
                        client, model, [text[:cutoff]], context_size
                    )
                )
                splitted_text.extend(
                    self._split_texts_to_fit_model_specs(
                        client, model, [text[cutoff:]], context_size
                    )
                )
            else:
                splitted_text.append((text, num_tokens))
        return splitted_text

    def get_num_tokens(
        self, model: str, credentials: dict, texts: list[str]
    ) -> list[int]:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return: list of estimated token counts
        """
        # Use _get_num_tokens_by_gpt2 as it provides a faster estimation of token counts
        # compared to using the count_tokens action for each text.
        return [self._get_num_tokens_by_gpt2(text) for text in texts]

    def _count_tokens(self, client: genai.Client, model: str, text: str) -> int:
        """
        Count the number of tokens in the given text using the specified model or GPT-2 as a fallback.

        :param client: model client
        :param model: model name
        :param text: text to embed
        :return: estimated token count
        """
        # in case the model does not support count_token action
        # we can use the flash-lite model to approximate the token count
        count_model = (
            model
            if "countTokens" in (client.models.get(model=model).supported_actions or [])
            else "gemini-2.0-flash-lite"
        )
        try:
            response = client.models.count_tokens(model=count_model, contents=[text])
            if tokens := response.total_tokens:
                return tokens
            return self._get_num_tokens_by_gpt2(text)
        except Exception as ex:
            raise RuntimeError(f"Error counting tokens: {ex}")

    def validate_credentials(self, model: str, credentials: Mapping) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            client = genai.Client(api_key=credentials["google_api_key"])
            client.models.embed_content(model=model, contents=["ping"])
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _embedding_invoke(
        self,
        model: str,
        client: genai.Client,
        texts: Union[list[str], str],
        input_type: EmbeddingInputType,
    ) -> list[EmbeddingTokenPair]:
        """
        Invoke embedding model

        :param model: model name
        :param client: model client
        :param texts: texts to embed
        :param extra_model_kwargs: extra model kwargs
        :return: embeddings and used tokens
        """

        # call embedding model
        task_type = to_task_type(input_type.value)
        config = EmbedContentConfig(task_type=task_type.name) if task_type else None
        response = client.models.embed_content(
            model=model, contents=texts, config=config
        )

        if response.embeddings is None:
            raise InvokeError(f"Unable to get embeddings from '{model}' model")

        result: list[tuple[list[float], Optional[int]]] = []
        for embedding in response.embeddings:
            embeddings = embedding.values or []
            used_tokens = (
                embedding.statistics.token_count if embedding.statistics else None
            )
            result.append((embeddings, int(used_tokens) if used_tokens else None))

        return result

    def _calc_response_usage(
        self, model: str, credentials: dict, tokens: int
    ) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: input tokens
        :return: usage
        """
        # get input price info
        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens,
        )

        # transform usage
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

    def _detect_image_mime_type(self, base64_str: str, validate_format: bool = False) -> str:
        """
        Detect image MIME type from base64 string

        :param base64_str: base64 string
        :param validate_format: if True, raise error for unsupported formats
        :return: MIME type (e.g., 'image/jpeg', 'image/png')
        """
        try:
            # Remove data URI prefix if present
            if "," in base64_str:
                base64_str = base64_str.split(",", 1)[1]

            data = base64.b64decode(base64_str, validate=True)

            # Check file signatures
            if data.startswith(b"\xFF\xD8\xFF"):
                return "image/jpeg"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
                mime = "image/gif"
            elif data.startswith(b"WEBP", 8):
                mime = "image/webp"
            else:
                mime = "image/jpeg"

            # Validate format for Gemini Embedding 2 (only JPEG and PNG are supported)
            if validate_format and mime not in self.SUPPORTED_IMAGE_FORMATS:
                raise ValueError(
                    f"Unsupported image format: {mime}. "
                    f"Gemini Embedding 2 only supports: {', '.join(sorted(self.SUPPORTED_IMAGE_FORMATS))}"
                )
            return mime
        except ValueError:
            raise
        except binascii.Error:
            logger.warning("Failed to decode base64 image data, defaulting to image/jpeg", exc_info=True)
            return "image/jpeg"

    def _get_output_dimension(self, model: str, credentials: dict) -> Optional[int]:
        """
        Get output dimension from model properties (for MRL support)

        :param model: model name
        :param credentials: model credentials
        :return: output dimension if configured, None otherwise
        """
        try:
            model_schema = self.get_model_schema(model, credentials)
            if model_schema and model_schema.model_properties:
                return model_schema.model_properties.get("output_dimension")
        except Exception:
            logger.warning("Failed to get output_dimension from model schema", exc_info=True)
        return None

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        documents: list[MultiModalContent],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> MultiModalEmbeddingResult:
        """
        Invoke multimodal embedding model

        :param model: model name
        :param credentials: model credentials
        :param documents: multimodal documents to embed
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        self.started_at = time.perf_counter()
        client = genai.Client(api_key=credentials["google_api_key"])

        # Convert MultiModalContent to Google Genai format, tracking content types
        contents = []        # converted content for API call
        content_is_image = []  # parallel list: True if image, False if text
        original_texts = []   # parallel list: original text string (or None for images)
        for document in documents:
            if document.content_type == MultiModalContentType.TEXT:
                contents.append(document.content)
                content_is_image.append(False)
                original_texts.append(document.content)
            elif document.content_type == MultiModalContentType.IMAGE:
                # Validate image format (Gemini Embedding 2 only supports JPEG and PNG)
                mime_type = self._detect_image_mime_type(document.content, validate_format=True)
                # Decode base64 and create Part object
                base64_str = document.content
                if "," in base64_str:
                    base64_str = base64_str.split(",", 1)[1]
                image_data = base64.b64decode(base64_str)
                part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
                contents.append(part)
                content_is_image.append(True)
                original_texts.append(None)
            else:
                raise ValueError(
                    f"Unsupported content type: {document.content_type}. "
                    f"Gemini Embedding 2 currently supports TEXT and IMAGE."
                )

        # Get model properties
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)

        # Batch processing if needed
        embeddings = []
        used_tokens = 0

        # Process in batches
        for i in range(0, len(contents), max_chunks):
            batch_contents = contents[i : i + max_chunks]

            # Validate per-batch image count limit
            # Gemini Embedding 2 supports at most 6 images per API request
            batch_image_count = sum(content_is_image[i : i + max_chunks])
            if batch_image_count > self.MAX_IMAGES_PER_REQUEST:
                raise ValueError(
                    f"Too many images in batch: {batch_image_count}. "
                    f"Gemini Embedding 2 supports at most {self.MAX_IMAGES_PER_REQUEST} images per request."
                )

            # Prepare config with optional output_dimension (MRL support)
            task_type = to_task_type(input_type.value)
            output_dimension = self._get_output_dimension(model, credentials)

            config_kwargs = {}
            if task_type:
                config_kwargs["task_type"] = task_type.name
            if output_dimension:
                config_kwargs["output_dimensionality"] = output_dimension

            config = EmbedContentConfig(**config_kwargs) if config_kwargs else None

            # Call embedding API
            response = client.models.embed_content(
                model=model, contents=batch_contents, config=config
            )

            if response.embeddings is None:
                raise InvokeError(
                    f"Unable to get embeddings from '{model}' model"
                )

            # Process embeddings
            batch_original_texts = original_texts[i : i + max_chunks]
            batch_is_image = content_is_image[i : i + max_chunks]
            for j, embedding in enumerate(response.embeddings):
                embedding_values = embedding.values or []
                embeddings.append(embedding_values)

                # Count tokens: prefer API statistics, then estimate by content type
                if embedding.statistics and embedding.statistics.token_count:
                    used_tokens += embedding.statistics.token_count
                elif batch_is_image[j]:
                    # Image: use fixed estimate
                    used_tokens += self.IMAGE_TOKEN_ESTIMATE
                elif batch_original_texts[j] is not None:
                    # Text: estimate using GPT-2 tokenizer
                    used_tokens += self._get_num_tokens_by_gpt2(batch_original_texts[j])
                else:
                    # Final fallback
                    used_tokens += self.IMAGE_TOKEN_ESTIMATE

        # Calculate usage
        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=used_tokens
        )

        return MultiModalEmbeddingResult(
            model=model,
            embeddings=embeddings,
            usage=usage,
        )
