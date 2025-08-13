from typing import Any, Optional
from dify_plugin import OAICompatText2SpeechModel


class Ai302TextToSpeechModel(OAICompatText2SpeechModel):
    """
    Model class for 302.AI text to speech model.
    """

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> Any:
        """
        Invoke text to speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to convert to speech
        :param voice: voice to use
        :param user: unique user id
        :return: audio file content
        """
        self._add_custom_parameters(credentials)
        
        # Get available voices for the model
        voices = self.get_tts_model_voices(model=model, credentials=credentials) or []
        
        # If voice is not provided or not in the available voices, use default
        if not voice or voice not in [d["value"] for d in voices]:
            voice = self._get_model_default_voice(model, credentials)
        
        # Call the parent class method to handle the actual invocation
        return super()._invoke(model, tenant_id, credentials, content_text, voice, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict) -> None:
        """
        Add custom parameters to credentials
        """
        credentials["endpoint_url"] = "https://api.302.ai/v1"