from typing import Mapping

from dify_plugin.entities.model import AIModelEntity, I18nObject
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.openai_compatible.text_embedding import OAICompatEmbeddingModel

from ..llm.llm import validate_lemonade_credentials


class LemonadeTextEmbeddingModel(OAICompatEmbeddingModel):

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        credentials = credentials or {}
        entity = super().get_customizable_model_schema(model, credentials)

        return entity

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials using shared validation utility.

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        # Use shared validation function
        validate_lemonade_credentials(credentials)
