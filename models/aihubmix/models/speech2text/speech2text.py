from typing import IO, Optional
from dify_plugin import OAICompatSpeech2TextModel


class AihubmixSpeech2TextModel(OAICompatSpeech2TextModel):
    """
    Model class for Aihubmix Speech to text model.
    """
    def _update_credential(self, credentials: dict):
        api_url = (credentials.get("api_url") or "https://aihubmix.com").rstrip("/")
        credentials["endpoint_url"] = f"{api_url}/v1"


    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        self._update_credential(credentials)
        return super()._invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credential(credentials)
        return super().validate_credentials(model, credentials)
