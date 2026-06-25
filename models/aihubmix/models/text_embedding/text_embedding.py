from typing import Optional
from dify_plugin import OAICompatEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult


class AihubmixTextEmbeddingModel(OAICompatEmbeddingModel):
    """
    Model class for Aihubmix text embedding model.
    """

    def _update_credential(self, credentials: dict):
        api_url = ((credentials.get("api_url_custom") if credentials.get("api_url") == "__custom__" else credentials.get("api_url")) or "https://aihubmix.com").rstrip("/")
        credentials["endpoint_url"] = f"{api_url}/v1"


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
