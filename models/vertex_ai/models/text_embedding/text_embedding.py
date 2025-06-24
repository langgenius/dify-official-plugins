import base64
import json
import time
from decimal import Decimal
from typing import Optional
from dify_plugin import TextEmbeddingModel
import tiktoken
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
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, TextEmbeddingResult
from dify_plugin.errors.model import CredentialsValidateFailedError
from google.cloud import aiplatform
from google.oauth2 import service_account
from vertexai.language_models import TextEmbeddingModel as VertexTextEmbeddingModel

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
        if service_account_info:
            service_accountSA = service_account.Credentials.from_service_account_info(service_account_info)
            aiplatform.init(credentials=service_accountSA, project=project_id, location=location, api_transport="rest")
        else:
            aiplatform.init(project=project_id, location=location, api_transport="rest")
        client = VertexTextEmbeddingModel.from_pretrained(model)
        (embeddings_batch, embedding_used_tokens) = self._embedding_invoke(client=client, texts=texts)
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
            if service_account_info:
                service_accountSA = service_account.Credentials.from_service_account_info(service_account_info)
                aiplatform.init(credentials=service_accountSA, project=project_id, location=location, api_transport="rest")
            else:
                aiplatform.init(project=project_id, location=location, api_transport="rest")
            client = VertexTextEmbeddingModel.from_pretrained(model)
            self._embedding_invoke(model=model, client=client, texts=["ping"])
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _embedding_invoke(self, client: VertexTextEmbeddingModel, texts: list[str]) -> [list[float], int]:
        """
        Invoke embedding model

        :param model: model name
        :param client: model client
        :param texts: texts to embed
        :return: embeddings and used tokens
        """
        response = client.get_embeddings(texts)
        embeddings = []
        token_usage = 0
        for i in range(len(response)):
            embeddings.append(response[i].values)
            token_usage += int(response[i].statistics.token_count)
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
