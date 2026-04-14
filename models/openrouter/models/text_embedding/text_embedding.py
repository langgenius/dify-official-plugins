from typing import Optional

from dify_plugin import OAICompatEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult

DEFAULT_ENDPOINT_URL = "https://openrouter.ai/api/v1"


def _normalize_endpoint_url(credentials: dict) -> str:
    endpoint_url = (
        (credentials.get("endpoint_url") or DEFAULT_ENDPOINT_URL).strip().rstrip("/")
    )
    return endpoint_url or DEFAULT_ENDPOINT_URL


class OpenRouterTextEmbeddingModel(OAICompatEmbeddingModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        self._update_credentials(credentials)
        return super()._invoke(model, credentials, texts, user, input_type)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credentials(credentials)
        super().validate_credentials(model, credentials)

    def get_num_tokens(
        self, model: str, credentials: dict, texts: list[str]
    ) -> list[int]:
        self._update_credentials(credentials)
        return super().get_num_tokens(model, credentials, texts)

    @staticmethod
    def _update_credentials(credentials: dict) -> None:
        credentials["endpoint_url"] = _normalize_endpoint_url(credentials)
        credentials["extra_headers"] = {
            "HTTP-Referer": "https://dify.ai/",
            "X-Title": "Dify",
        }
