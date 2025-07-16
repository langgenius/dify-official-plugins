from typing import Optional
from dify_plugin import OAICompatEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult


class AihubmixTextEmbeddingModel(OAICompatEmbeddingModel):
    """
    Model class for Aihubmix text embedding model.
    """

    def _update_credential(self, credentials: dict):
        credentials["endpoint_url"] = "https://aihubmix.com/v1"


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
        self._update_credential(credentials)
        return super()._invoke(model, credentials, texts, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credential(credentials)
        super().validate_credentials(model, credentials)

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> int:
        self._update_credential(credentials)
        return super().get_num_tokens(model, credentials, texts)
