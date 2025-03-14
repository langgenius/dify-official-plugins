from typing import Mapping

from dify_plugin.entities.model import (
    AIModelEntity,
    I18nObject
)

from dify_plugin.interfaces.model.openai_compatible.text_embedding import (
    OAICompatEmbeddingModel,
)


class OpenAITextEmbeddingModel(OAICompatEmbeddingModel):

    def get_customizable_model_schema(self, model: str, credentials: Mapping) -> AIModelEntity:
        entity = super().get_customizable_model_schema(model, credentials)

        if "show_name" in credentials and credentials["show_name"] != "":
            entity.label= I18nObject(
                en_US=credentials["show_name"],
                zh_Hans=credentials["show_name"]
            )

        return entity
