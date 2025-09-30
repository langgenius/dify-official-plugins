from typing import IO, Optional
from dify_plugin import OAICompatSpeech2TextModel


class SambaNovaSpeech2TextModel(OAICompatSpeech2TextModel):
    """
    Model class for SambaNova Speech to text models.
    """

    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        self._add_custom_parameters(credentials)
        return super()._invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        return super().validate_credentials(model, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict) -> None:
        credentials["endpoint_url"] = "https://api.sambanova.ai/v1"