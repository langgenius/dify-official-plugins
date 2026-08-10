from typing import Any, Optional

from dify_plugin.entities.model import AIModelEntity
from dify_plugin.interfaces.model.openai_compatible.tts import OAICompatText2SpeechModel

from ..llm.llm import validate_lemonade_credentials


class LemonadeText2SpeechModel(OAICompatText2SpeechModel):
    """
    Text-to-speech model backed by Lemonade's OpenAI-compatible
    ``/api/v1/audio/speech`` endpoint (Kokoro recipes).
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
        return super()._invoke(
            model, tenant_id, self._to_lemonade_credentials(credentials), content_text, voice, user
        )

    def validate_credentials(
        self, model: str, credentials: dict, user: Optional[str] = None
    ) -> None:
        # Reuse the shared server health + model availability check.
        validate_lemonade_credentials(credentials, model)

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        return super().get_customizable_model_schema(
            model, self._to_lemonade_credentials(credentials)
        )

    def get_tts_model_voices(
        self, model: str, credentials: dict, language: Optional[str] = None
    ) -> list:
        return super().get_tts_model_voices(
            model, self._to_lemonade_credentials(credentials), language
        )

    @staticmethod
    def _to_lemonade_credentials(credentials: dict) -> dict:
        """
        Inject the fixed Lemonade API key and ensure the endpoint targets the
        ``/api/v1`` base expected by the OpenAI-compatible TTS implementation.
        """
        creds = dict(credentials)
        creds.setdefault("api_key", "lemonade")

        endpoint_url = (creds.get("endpoint_url") or "").rstrip("/")
        if endpoint_url and "/api/v1" not in endpoint_url:
            endpoint_url += "/api/v1"
        creds["endpoint_url"] = endpoint_url
        return creds
