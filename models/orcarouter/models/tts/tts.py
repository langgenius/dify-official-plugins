from collections.abc import Generator
from typing import Optional

from dify_plugin import OAICompatText2SpeechModel

from models._endpoint_utils import normalize_endpoint_url


class OrcaRouterText2SpeechModel(OAICompatText2SpeechModel):
    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        self._update_credentials(credentials)
        return super()._invoke(model, tenant_id, credentials, content_text, voice, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credentials(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _update_credentials(credentials: dict) -> None:
        credentials["endpoint_url"] = normalize_endpoint_url(credentials)
