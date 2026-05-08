from __future__ import annotations

from collections.abc import Generator
from typing import Optional

import requests
from dify_plugin import TTSModel
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError

from ..common_telnyx import _CommonTelnyx


class TelnyxText2SpeechModel(_CommonTelnyx, TTSModel):
    """Telnyx text-to-speech model."""

    TTS_PATH = "/v2/text-to-speech/speech"

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> bytes | Generator[bytes, None, None]:
        return self._tts_invoke_streaming(model=model, credentials=credentials, content_text=content_text, voice=voice)

    def validate_credentials(self, model: str, credentials: dict, user: Optional[str] = None) -> None:
        try:
            b"".join(
                self._tts_invoke_streaming(
                    model=model,
                    credentials=credentials,
                    content_text="Hello Dify!",
                    voice=self._get_model_default_voice(model, credentials),
                )
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> Generator[bytes, None, None]:
        if not content_text:
            raise InvokeBadRequestError("content_text is required")
        voice = voice or self._get_model_default_voice(model, credentials)
        payload = {
            "text": content_text,
            "voice": voice,
            "output_format": self._get_model_audio_type(model, credentials) or "mp3",
        }
        # Telnyx currently selects the TTS backend from the voice name. Keep model for forwards compatibility.
        if model:
            payload["model"] = model
        response = requests.post(
            self._build_url(credentials, self.TTS_PATH),
            headers=self._get_headers(credentials),
            json=payload,
            timeout=(10, 300),
            stream=True,
        )
        self._raise_for_response(response)
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                yield chunk
