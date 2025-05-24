from typing import IO, Optional
from collections.abc import Generator
from dify_plugin import OAICompatText2SpeechModel


class AihubmixText2SpeechModel(OAICompatText2SpeechModel):
    """
    Model class for Aihubmix Text to Speech model.
    """

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        """
        _invoke text2speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :param user: unique user id
        :return: text translated to audio file
        """
    
        credentials["endpoint_url"] = "https://aihubmix.com/v1"
        return super()._invoke(model, tenant_id, credentials, content_text, voice, user)
    

