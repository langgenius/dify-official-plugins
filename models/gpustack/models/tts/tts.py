from typing import Any, Optional
from dify_plugin.interfaces.model.openai_compatible.tts import OAICompatText2SpeechModel


class GPUStackTextToSpeechModel(OAICompatText2SpeechModel):
    """
    Model class for GPUStack Text to Speech model.
    """

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: str | None = None,
    ) -> Any:
        model = model.strip()
        compatible_credentials = self._get_compatible_credentials(credentials)
        return super()._invoke(model, tenant_id, compatible_credentials, content_text, voice, user)

    def validate_credentials(self, model: str, credentials: dict, user: Optional[str] = None) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :param user: unique user id
        """
        compatible_credentials = self._get_compatible_credentials(credentials)
        super().validate_credentials(model, compatible_credentials)

    def _get_compatible_credentials(self, credentials: dict) -> dict:
        """
        Get compatible credentials

        :param credentials: model credentials
        :return: compatible credentials
        """
        compatible_credentials = credentials.copy()
        base_url = credentials["endpoint_url"].rstrip("/").removesuffix("/v1").removesuffix("/v1-openai")
        compatible_credentials["endpoint_url"] = f"{base_url}/v1"

        return compatible_credentials
