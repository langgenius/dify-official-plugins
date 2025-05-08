import time
from typing import Optional

import numpy as np
from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import CredentialsValidateFailedError
from google import genai
from google.genai import 위험한_사용자_입력_오류 as GoogleAPIErrors  # Using an alias to avoid potential name collisions if 'errors' is used elsewhere
from google.generativeai import types as genai_types


class GeminiTextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for Google Gemini text embedding model.
    """

    def _invoke(
        self,
        model: str,  # e.g., "embedding-001" or "text-embedding-004"
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,  # User is not directly used by Gemini embedding API
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        api_key = credentials.get("api_key")
        if not api_key:
            raise CredentialsValidateFailedError("API key is missing in credentials.")

        try:
            genai.configure(api_key=api_key)
        except Exception as e:
            raise CredentialsValidateFailedError(f"Failed to configure Gemini API: {e}")

        gemini_model_name = f"models/{model}"
        try:
            embedding_model_info = genai.get_model(gemini_model_name)
            token_limit_per_text = getattr(embedding_model_info, 'input_token_limit', 2048)
            if model == "text-embedding-004":  # Explicitly set for known model
                token_limit_per_text = 2048
            elif "gemini-" in model:  # For generative models used for embedding, limit might be higher
                pass
        except Exception as e:
            raise CredentialsValidateFailedError(f"Failed to get model info for {gemini_model_name}: {e}")

        task_type_map = {
            EmbeddingInputType.DOCUMENT: genai_types.TaskType.RETRIEVAL_DOCUMENT,
            EmbeddingInputType.QUERY: genai_types.TaskType.RETRIEVAL_QUERY,
        }
        gemini_task_type = task_type_map.get(input_type, genai_types.TaskType.RETRIEVAL_DOCUMENT)

        all_text_chunks_to_embed: list[str] = []
        chunk_to_original_text_indices: list[int] = []
        token_counts_for_chunks: list[int] = []

        for original_idx, text_content in enumerate(texts):
            if not text_content:  # Handle empty strings
                all_text_chunks_to_embed.append("")
                chunk_to_original_text_indices.append(original_idx)
                token_counts_for_chunks.append(0)
                continue

            try:
                current_text_tokens = embedding_model_info.count_tokens(text_content).total_tokens
            except Exception:
                current_text_tokens = len(text_content) // 4  # Rough estimate if count fails

            if current_text_tokens <= token_limit_per_text:
                all_text_chunks_to_embed.append(text_content)
                chunk_to_original_text_indices.append(original_idx)
                token_counts_for_chunks.append(current_text_tokens)
            else:
                words = text_content.split()
                current_chunk_text = ""
                for word in words:
                    test_chunk = f"{current_chunk_text} {word}".strip()
                    try:
                        chunk_tokens = embedding_model_info.count_tokens(test_chunk).total_tokens
                    except Exception:
                        chunk_tokens = len(test_chunk) // 4  # Rough estimate

                    if chunk_tokens <= token_limit_per_text:
                        current_chunk_text = test_chunk
                    else:
                        if current_chunk_text:  # Add the previous valid chunk
                            all_text_chunks_to_embed.append(current_chunk_text)
                            chunk_to_original_text_indices.append(original_idx)
                            token_counts_for_chunks.append(embedding_model_info.count_tokens(current_chunk_text).total_tokens)

                        try:
                            word_tokens = embedding_model_info.count_tokens(word).total_tokens
                        except Exception:
                            word_tokens = len(word) // 4

                        if word_tokens <= token_limit_per_text:
                            current_chunk_text = word
                        else:
                            truncated_word = word
                            while embedding_model_info.count_tokens(truncated_word).total_tokens > token_limit_per_text and len(truncated_word) > 1:
                                truncated_word = truncated_word[:-1]
                            if truncated_word:
                                all_text_chunks_to_embed.append(truncated_word)
                                chunk_to_original_text_indices.append(original_idx)
                                token_counts_for_chunks.append(embedding_model_info.count_tokens(truncated_word).total_tokens)
                            current_chunk_text = ""

                if current_chunk_text:  # Add any remaining chunk
                    all_text_chunks_to_embed.append(current_chunk_text)
                    chunk_to_original_text_indices.append(original_idx)
                    token_counts_for_chunks.append(embedding_model_info.count_tokens(current_chunk_text).total_tokens)

                if not any(idx == original_idx for idx in chunk_to_original_text_indices) and text_content:
                    fallback_text = text_content
                    while embedding_model_info.count_tokens(fallback_text).total_tokens > token_limit_per_text and len(fallback_text) > 1:
                        fallback_text = fallback_text[:-max(1, int(len(fallback_text) * 0.1))]
                    if fallback_text:
                        all_text_chunks_to_embed.append(fallback_text)
                        chunk_to_original_text_indices.append(original_idx)
                        token_counts_for_chunks.append(embedding_model_info.count_tokens(fallback_text).total_tokens)
                    else:
                        all_text_chunks_to_embed.append("")
                        chunk_to_original_text_indices.append(original_idx)
                        token_counts_for_chunks.append(0)

        MAX_BATCH_SIZE_API = 100  # Gemini embed_content limit
        batched_embeddings_from_api: list[list[float]] = []

        actual_processed_tokens_count = 0

        if not all_text_chunks_to_embed and not texts:  # No input texts, no chunks
            final_embeddings: list[list[float]] = []
        elif not all_text_chunks_to_embed and texts:  # Input texts were there, but all resulted in no chunks
            try:
                sample_embedding_response = genai.embed_content(model=gemini_model_name, content=["a"], task_type=gemini_task_type)
                dim = len(sample_embedding_response['embedding'][0])
                zero_embedding = [0.0] * dim
            except Exception:
                zero_embedding = [0.0] * 768  # Common dimension
            final_embeddings = [list(zero_embedding) for _ in texts]
            actual_processed_tokens_count = 0
        else:
            for i in range(0, len(all_text_chunks_to_embed), MAX_BATCH_SIZE_API):
                batch_of_text_chunks = all_text_chunks_to_embed[i:i + MAX_BATCH_SIZE_API]
                try:
                    response = genai.embed_content(
                        model=gemini_model_name,
                        content=batch_of_text_chunks,
                        task_type=gemini_task_type
                    )
                    batched_embeddings_from_api.extend(response['embedding'])
                except GoogleAPIErrors.GoogleAPIError as e:
                    is_all_empty = all(not chunk for chunk in batch_of_text_chunks)
                    if is_all_empty:
                        try:
                            sample_embedding_response = genai.embed_content(model=gemini_model_name, content=["a"], task_type=gemini_task_type)
                            dim = len(sample_embedding_response['embedding'][0])
                            zero_embedding = [0.0] * dim
                        except Exception:
                            zero_embedding = [0.0] * 768  # Fallback dimension
                        batched_embeddings_from_api.extend([list(zero_embedding) for _ in batch_of_text_chunks])
                    else:
                        raise ConnectionError(f"Gemini API error: {e}")
                except Exception as e:
                    raise ConnectionError(f"Error calling Gemini embedding API: {e}")

            actual_processed_tokens_count = sum(token_counts_for_chunks)

            final_embeddings = [[] for _ in range(len(texts))]
            chunk_embeddings_for_each_original_text: list[list[list[float]]] = [[] for _ in range(len(texts))]
            chunk_token_counts_for_each_original_text: list[list[int]] = [[] for _ in range(len(texts))]

            for i_chunk in range(len(all_text_chunks_to_embed)):
                original_text_idx = chunk_to_original_text_indices[i_chunk]
                if i_chunk < len(batched_embeddings_from_api):
                    chunk_embedding = batched_embeddings_from_api[i_chunk]
                    chunk_tokens = token_counts_for_chunks[i_chunk]
                    chunk_embeddings_for_each_original_text[original_text_idx].append(chunk_embedding)
                    chunk_token_counts_for_each_original_text[original_text_idx].append(chunk_tokens)

            for i_orig_text in range(len(texts)):
                embeddings_for_this_original_text = chunk_embeddings_for_each_original_text[i_orig_text]
                tokens_for_this_original_text_chunks = chunk_token_counts_for_each_original_text[i_orig_text]

                if not embeddings_for_this_original_text:
                    try:
                        sample_embedding_response = genai.embed_content(model=gemini_model_name, content=["a"], task_type=gemini_task_type)
                        dim = len(sample_embedding_response['embedding'][0])
                        avg_embedding_np = np.array([0.0] * dim)
                    except Exception:
                        avg_embedding_np = np.array([0.0] * 768)
                elif len(embeddings_for_this_original_text) == 1:
                    avg_embedding_np = np.array(embeddings_for_this_original_text[0])
                else:
                    if sum(tokens_for_this_original_text_chunks) == 0:
                        avg_embedding_np = np.mean(embeddings_for_this_original_text, axis=0)
                    else:
                        avg_embedding_np = np.average(
                            embeddings_for_this_original_text, axis=0, weights=tokens_for_this_original_text_chunks
                        )

                norm = np.linalg.norm(avg_embedding_np)
                if norm < 1e-9:
                    normalized_embedding_list = avg_embedding_np.tolist()
                else:
                    normalized_embedding_list = (avg_embedding_np / norm).tolist()

                if np.isnan(np.sum(normalized_embedding_list)):
                    try:
                        sample_embedding_response = genai.embed_content(model=gemini_model_name, content=["a"], task_type=gemini_task_type)
                        dim = len(sample_embedding_response['embedding'][0])
                        final_embeddings[i_orig_text] = [0.0] * dim
                    except Exception:
                        final_embeddings[i_orig_text] = [0.0] * 768
                else:
                    final_embeddings[i_orig_text] = normalized_embedding_list

        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=actual_processed_tokens_count
        )

        return TextEmbeddingResult(embeddings=final_embeddings, usage=usage, model=model)

    def get_num_tokens(
        self, model: str, credentials: dict, texts: list[str]
    ) -> list[int]:
        api_key = credentials.get("api_key")
        if not api_key:
            return [0] * len(texts)

        try:
            genai.configure(api_key=api_key)
        except Exception:
            return [0] * len(texts)

        gemini_model_name = f"models/{model}"
        try:
            embedding_model_info = genai.get_model(gemini_model_name)
        except Exception:
            return [len(text) // 4 for text in texts]

        num_tokens_list = []
        for text_content in texts:
            if not text_content:
                num_tokens_list.append(0)
            else:
                try:
                    count = embedding_model_info.count_tokens(text_content).total_tokens
                    num_tokens_list.append(count)
                except Exception:
                    num_tokens_list.append(len(text_content) // 4)
        return num_tokens_list

    def validate_credentials(self, model: str, credentials: dict) -> None:
        api_key = credentials.get("api_key")
        if not api_key:
            raise CredentialsValidateFailedError("API key is missing in credentials.")

        try:
            genai.configure(api_key=api_key)
        except Exception as e:
            raise CredentialsValidateFailedError(f"Failed to configure Gemini API during validation: {e}")

        gemini_model_name = f"models/{model}"

        try:
            genai.embed_content(
                model=gemini_model_name,
                content="ping",
                task_type=genai_types.TaskType.RETRIEVAL_DOCUMENT
            )
        except GoogleAPIErrors.PermissionDenied as e:
            raise CredentialsValidateFailedError(f"Invalid API key or insufficient permissions: {e}")
        except GoogleAPIErrors.InvalidArgumentError as e:
            raise CredentialsValidateFailedError(f"Invalid argument, possibly model name '{gemini_model_name}' is incorrect or not supported for embedding: {e}")
        except GoogleAPIErrors.GoogleAPIError as e:
            raise CredentialsValidateFailedError(f"Gemini API error during validation: {e}")
        except Exception as ex:
            raise CredentialsValidateFailedError(f"An unexpected error occurred during credential validation: {str(ex)}")

    def _calc_response_usage(
        self, model: str, credentials: dict, tokens: int
    ) -> EmbeddingUsage:
        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens,
        )

        usage = EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - getattr(self, 'started_at', time.perf_counter()),
        )
        return usage
