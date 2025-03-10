from typing import Optional

from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult
from dify_plugin.interfaces.model.openai_compatible.text_embedding import (
    OAICompatEmbeddingModel,
)


class NetmindTextEmbeddingModel(OAICompatEmbeddingModel):
    def _update_endpoint_url(self, credentials: dict) -> dict:
        credentials["endpoint_url"] = "https://api.netmind.ai/inference-api/openai/v1"
        return credentials

    def validate_credentials(self, model: str, credentials: dict) -> None:
        cred_with_endpoint = self._update_endpoint_url(credentials=credentials)
        return super().validate_credentials(model, cred_with_endpoint)

    def invoke(
            self,
            model: str,
            credentials: dict,
            texts: list[str],
            user: Optional[str] = None,
            input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        cred_with_endpoint = self._update_endpoint_url(credentials=credentials)
        return super().invoke(model, cred_with_endpoint, texts, user, input_type)

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        cred_with_endpoint = self._update_endpoint_url(credentials=credentials)
        return super().get_num_tokens(model, cred_with_endpoint, texts)
