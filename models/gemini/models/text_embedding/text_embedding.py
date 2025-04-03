import re
import time
import numpy as np
from typing import Optional, Union
from collections.abc import Mapping

from google import genai
from google.genai.types import EmbedContentConfig
from google.generativeai.embedding import to_task_type

from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, TextEmbeddingResult
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError

from ..common_gemini import _CommonGemini

type EmbeddingTokenPair = tuple[list[float], Optional[int]]  # Embedding and number of tokens used


class GeminiTextEmbeddingModel(_CommonGemini, TextEmbeddingModel):
    """
    Model class for Gemini text embedding model.
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
        :return: embeddings result
        """
        client = genai.Client(api_key=credentials["google_api_key"])

        # get model properties
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)

        # splitted texts in case the chunks are bigger than the context size
        splitted_texts = [self._split_texts_to_fit_model_specs(client, model, [text], context_size) for text in texts]

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
                [used_token or chunk_size for used_token, [_, chunk_size] in zip(num_tokens, splitted_texts[i])]
            )

        # calc usage
        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=used_tokens)

        return TextEmbeddingResult(embeddings=merged_embeddings, usage=usage, model=model)

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
                    self._split_texts_to_fit_model_specs(client, model, [text[:cutoff]], context_size)
                )
                splitted_text.extend(
                    self._split_texts_to_fit_model_specs(client, model, [text[cutoff:]], context_size)
                )
            else:
                splitted_text.append((text, num_tokens))
        return splitted_text

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
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
        response = client.models.embed_content(model=model, contents=texts, config=config)

        if response.embeddings is None:
            raise InvokeError(f"Unable to get embeddings from '{model}' model")

        result: list[tuple[list[float], Optional[int]]] = []
        for embedding in response.embeddings:
            embeddings = embedding.values or []
            used_tokens = embedding.statistics.token_count if embedding.statistics else None
            result.append((embeddings, int(used_tokens) if used_tokens else None))

        return result

    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
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
