from typing import IO, Optional

from dify_plugin import OAICompatSpeech2TextModel


class GiteeAISpeech2TextModel(OAICompatSpeech2TextModel):
    """
    Model class for GiteeAI Speech to text model.
    """
    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        self._add_custom_parameters(credentials)
        return super()._invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        return super().validate_credentials(model, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict) -> None:
        credentials["endpoint_url"] = "https://ai.gitee.com/v1"
