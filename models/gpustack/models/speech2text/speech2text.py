from typing import Optional

from dify_plugin import OAICompatSpeechToTextModel
from dify_plugin.entities.model.speech2text import SpeechToTextResult


class GPUStackSpeechToTextModel(OAICompatSpeechToTextModel):
    """
    Model class for GPUStack Speech to text model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        audio: bytes,
        user: Optional[str] = None,
    ) -> SpeechToTextResult:
        compatible_credentials = self._get_compatible_credentials(credentials)
        return super()._invoke(model, compatible_credentials, audio, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        """
        compatible_credentials = self._get_compatible_credentials(credentials)
        super().validate_credentials(model, compatible_credentials)

    def _get_compatible_credentials(self, credentials: dict) -> dict:
        credentials = credentials.copy()
        base_url = credentials["endpoint_url"].rstrip("/").removesuffix("/v1")
        credentials["endpoint_url"] = f"{base_url}/v1"
        return credentials
