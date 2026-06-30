from typing import IO, Optional
from urllib.parse import urljoin

import requests

from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelType
from dify_plugin.errors.model import InvokeBadRequestError
from dify_plugin.interfaces.model.openai_compatible.speech2text import OAICompatSpeech2TextModel

from ..llm.llm import validate_lemonade_credentials


def _lemonade_base_url(credentials: dict) -> str:
    """
    Normalize the configured endpoint to the Lemonade ``/api/v1`` base URL
    (with a trailing slash so ``urljoin`` keeps the version prefix).
    """
    endpoint_url = (credentials.get("endpoint_url") or "").rstrip("/")
    if endpoint_url and "/api/v1" not in endpoint_url:
        endpoint_url += "/api/v1"
    return endpoint_url + "/"


class LemonadeSpeech2TextModel(OAICompatSpeech2TextModel):
    """
    Speech-to-text model backed by Lemonade's OpenAI-compatible
    ``/api/v1/audio/transcriptions`` endpoint (Whisper recipes).
    """

    def _invoke(
        self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None
    ) -> str:
        # Lemonade uses a fixed, unused API key.
        headers = {"Authorization": "Bearer lemonade"}

        endpoint_url = urljoin(_lemonade_base_url(credentials), "audio/transcriptions")

        language = credentials.get("language") or "en"
        prompt = credentials.get("initial_prompt") or "convert the audio to text"
        payload = {"model": model, "language": language, "prompt": prompt}
        files = [("file", file)]

        response = requests.post(
            endpoint_url, headers=headers, data=payload, files=files, timeout=(10, 300)
        )

        if response.status_code != 200:
            raise InvokeBadRequestError(response.text)
        return response.json()["text"]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        # Reuse the shared server health + model availability check.
        validate_lemonade_credentials(credentials, model)

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={},
            parameter_rules=[],
        )
        return entity
