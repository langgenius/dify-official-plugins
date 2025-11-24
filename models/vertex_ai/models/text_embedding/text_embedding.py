import base64
import json
import time
from decimal import Decimal
from typing import Optional

import tiktoken
from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    PriceConfig,
    PriceType,
)
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    MultiModalContent,
    MultiModalEmbeddingResult,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import CredentialsValidateFailedError
from google import genai
from google.genai import types
from google.oauth2 import service_account

from models.common import CommonVertexAi


class VertexAiTextEmbeddingModel(CommonVertexAi, TextEmbeddingModel):
    """
    Model class for Vertex AI text embedding model.
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
        service_account_info = (
            json.loads(base64.b64decode(service_account_key))
            if (
                service_account_key := credentials.get("vertex_service_account_key", "")
            )
            else None
        )
        project_id = credentials["vertex_project_id"]
        location = credentials["vertex_location"]
        
        # Initialize GenAI client
        if service_account_info:
            SCOPES = [
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/generative-language"
            ]
            credential = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=credential
            )
        else:
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location
            )
        
        (embeddings_batch, embedding_used_tokens) = self._embedding_invoke(
            client=client, 
            model=model,
            texts=texts,
            input_type=input_type
        )
        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=embedding_used_tokens)
        return TextEmbeddingResult(embeddings=embeddings_batch, usage=usage, model=model)

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
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        tokens = []
        for text in texts:
            tokenized_text = enc.encode(text)
            tokens.append(len(tokenized_text))
        return tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            service_account_info = (
                json.loads(base64.b64decode(service_account_key))
                if (
                    service_account_key := credentials.get("vertex_service_account_key", "")
                )
                else None
            )
            project_id = credentials["vertex_project_id"]
            location = credentials["vertex_location"]
            
            # Initialize GenAI client
            if service_account_info:
                SCOPES = [
                    "https://www.googleapis.com/auth/cloud-platform",
                    "https://www.googleapis.com/auth/generative-language"
                ]
                credential = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=SCOPES
                )
                client = genai.Client(
                    vertexai=True,
                    project=project_id,
                    location=location,
                    credentials=credential
                )
            else:
                client = genai.Client(
                    vertexai=True,
                    project=project_id,
                    location=location
                )
            
            # Test embedding with a simple text
            self._embedding_invoke(client=client, model=model, texts=["ping"])
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _embedding_invoke(
        self, 
        client: genai.Client, 
        model: str,
        texts: list[str],
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT
    ) -> tuple[list[list[float]], int]:
        """
        Invoke embedding model

        :param client: GenAI client
        :param model: model name
        :param texts: texts to embed
        :param input_type: input type
        :return: embeddings and used tokens
        """
        # Map Dify input types to GenAI task types
        task_type_mapping = {
            EmbeddingInputType.DOCUMENT: "RETRIEVAL_DOCUMENT",
            EmbeddingInputType.QUERY: "RETRIEVAL_QUERY",
        }
        task_type = task_type_mapping.get(input_type, "RETRIEVAL_DOCUMENT")
        
        embeddings = []
        token_usage = 0

        # Process each text individually with GenAI SDK
        for text in texts:
            response = client.models.embed_content(
                model=model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type
                )
            )
            
            # Extract embeddings
            if hasattr(response, 'embeddings') and response.embeddings:
                embedding_values = response.embeddings[0].values
                embeddings.append(embedding_values)
                
                # Estimate token count (GenAI SDK doesn't always provide token count)
                # Use tiktoken as fallback
                if hasattr(response, 'usage_metadata') and hasattr(response.usage_metadata, 'prompt_token_count'):
                    token_usage += response.usage_metadata.prompt_token_count
                else:
                    # Fallback to estimation
                    try:
                        enc = tiktoken.get_encoding("cl100k_base")
                        token_usage += len(enc.encode(text))
                    except Exception:
                        # Rough estimation: 1 token ≈ 4 characters
                        token_usage += len(text) // 4
        
        return (embeddings, token_usage)

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

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        """
        generate custom model entities from credentials
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.TEXT_EMBEDDING,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 512)),
                ModelPropertyKey.MAX_CHUNKS: 1,
            },
            parameter_rules=[],
            pricing=PriceConfig(
                input=Decimal(credentials.get("input_price", 0)),
                unit=Decimal(credentials.get("unit", 0)),
                currency=credentials.get("currency", "USD"),
            ),
        )
        return entity
    
    def _invoke_multimodal(
        self,
        model: str, 
        credentials: dict, 
        documents: list[MultiModalContent], 
        user: str | None = None, 
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT) -> MultiModalEmbeddingResult:
        """
        Invoke multimodal embedding model
        """
        service_account_info = (
            json.loads(base64.b64decode(service_account_key))
            if (
                service_account_key := credentials.get("vertex_service_account_key", "")
            )
            else None
        )
        project_id = credentials["vertex_project_id"]
        location = credentials["vertex_location"]
        
        # Initialize GenAI client
        if service_account_info:
            SCOPES = [
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/generative-language"
            ]
            credential = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=credential
            )
        else:
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location
            )
        
        (embeddings_batch, embedding_used_tokens) = self._multimodal_embedding_invoke(
            client=client, 
            model=model,
            documents=documents,
            input_type=input_type
        )
        usage = self._calc_response_usage(model=model, credentials=credentials, tokens=embedding_used_tokens)
        result = MultiModalEmbeddingResult(
            model=model,
            embeddings=embeddings_batch,
            usage=usage,
        )
        return result

    def _multimodal_embedding_invoke(
        self, 
        client: genai.Client, 
        model: str,
        documents: list[MultiModalContent],
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT
    ) -> tuple[list[list[float]], int]:
        """
        Invoke embedding model

        :param client: GenAI client
        :param model: model name
        :param texts: texts to embed
        :param input_type: input type
        :return: embeddings and used tokens
        """
        # Map Dify input types to GenAI task types
        task_type_mapping = {
            EmbeddingInputType.DOCUMENT: "RETRIEVAL_DOCUMENT",
            EmbeddingInputType.QUERY: "RETRIEVAL_QUERY",
        }
        task_type = task_type_mapping.get(input_type, "RETRIEVAL_DOCUMENT")
        
        embeddings = []
        token_usage = 0

        # Process each text individually with GenAI SDK
        for document in documents:
            response = client.models.embed_content(
                model=model,
                contents=document.content,
                config=types.EmbedContentConfig(
                    task_type=task_type
                )
            )
            
            # Extract embeddings
            if hasattr(response, 'embeddings') and response.embeddings:
                embedding_values = response.embeddings[0].values
                embeddings.append(embedding_values)
                
                # Estimate token count (GenAI SDK doesn't always provide token count)
                # Use tiktoken as fallback
                if hasattr(response, 'usage_metadata') and hasattr(response.usage_metadata, 'prompt_token_count'):
                    token_usage += response.usage_metadata.prompt_token_count
                else:
                    # Fallback to estimation for multimodal content
                    content_text = ""
                    if isinstance(document.content, str):
                        content_text = document.content
                    elif isinstance(document.content, list):
                        # Extract text from multimodal content parts
                        for part in document.content:
                            if isinstance(part, dict) and 'text' in part:
                                content_text += part.get('text', '')
                            elif isinstance(part, str):
                                content_text += part
                    
                    if content_text:
                        try:
                            enc = tiktoken.get_encoding("cl100k_base")
                            token_usage += len(enc.encode(content_text))
                        except Exception:
                            # Rough estimation: 1 token ≈ 4 characters
                            token_usage += len(content_text) // 4
                    else:
                        # For image-only content, estimate based on typical image token count
                        # Most vision models use ~85 tokens per image at standard resolution
                        token_usage += 85
        
        return (embeddings, token_usage)