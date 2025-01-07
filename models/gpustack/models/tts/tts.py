from collections.abc import Generator
from dify_plugin import OAICompatTextToSpeechModel
from dify_plugin.entities.model.tts import TTSResult


class GPUStackTextToSpeechModel(OAICompatTextToSpeechModel):
    """
    Model class for GPUStack Text to Speech model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        text: str,
        user: str | None = None,
    ) -> TTSResult | Generator:
        compatible_credentials = self._get_compatible_credentials(credentials)
        return super()._invoke(model, compatible_credentials, text, user)

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
        base_url = credentials["endpoint_url"].rstrip("/").removesuffix("/v1-openai")
        compatible_credentials["endpoint_url"] = f"{base_url}/v1-openai"

        return compatible_credentials
