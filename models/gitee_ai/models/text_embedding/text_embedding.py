from typing import Optional
from dify_plugin import OAICompatEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult


class GiteeAIEmbeddingModel(OAICompatEmbeddingModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        self._add_custom_parameters(credentials, model)
        return super()._invoke(model, credentials, texts, user, input_type)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials, None)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _add_custom_parameters(credentials: dict, model: str) -> None:
        credentials["endpoint_url"] = f"https://ai.gitee.com/v1/"
