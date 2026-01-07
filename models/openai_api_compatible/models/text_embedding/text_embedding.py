from typing import Mapping, Optional

from dify_plugin.entities.model import AIModelEntity, EmbeddingInputType, I18nObject
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult

from dify_plugin.interfaces.model.openai_compatible.text_embedding import OAICompatEmbeddingModel

from ..common_openai import _CommonOpenAI


class OpenAITextEmbeddingModel(_CommonOpenAI, OAICompatEmbeddingModel):

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        credentials = credentials or {}
        entity = super().get_customizable_model_schema(model, credentials)

        if "display_name" in credentials and credentials["display_name"] != "":
            entity.label = I18nObject(
                en_US=credentials["display_name"], zh_Hans=credentials["display_name"]
            )

        return entity

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

        prefix = self._get_prefix(credentials, input_type)
        texts = self._add_prefix(texts, prefix)

        return super()._invoke(model, credentials, texts, user)

    def _get_prefix(self, credentials: dict, input_type: EmbeddingInputType) -> str:
        if input_type == EmbeddingInputType.DOCUMENT:
            return credentials.get("document_prefix", "")

        if input_type == EmbeddingInputType.QUERY:
            return credentials.get("query_prefix", "")

        return ""

    def _add_prefix(self, texts: list[str], prefix: str) -> list[str]:
        return [f"{prefix} {text}" for text in texts] if prefix else texts
