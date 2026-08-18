from typing import Mapping, Optional

from dify_plugin.entities.model import AIModelEntity, EmbeddingInputType, I18nObject
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.openai_compatible.text_embedding import OAICompatEmbeddingModel

from ..llm.llm import validate_lemonade_credentials


class LemonadeTextEmbeddingModel(OAICompatEmbeddingModel):

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        # Lemonade serves its OpenAI-compatible API under /api/v1. The base class
        # posts to {endpoint_url}/embeddings, so without /api/v1 the request hits
        # {host}/embeddings and 404s (issue #3491). The LLM path already applies
        # this normalization in _add_custom_parameters; mirror it here, guarding
        # against an endpoint that already contains /api/v1.
        if "endpoint_url" in credentials and "/api/v1" not in credentials["endpoint_url"]:
            credentials["endpoint_url"] = credentials["endpoint_url"].rstrip("/") + "/api/v1"
        return super()._invoke(model, credentials, texts, user, input_type)

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
        validate_lemonade_credentials(credentials, model)
