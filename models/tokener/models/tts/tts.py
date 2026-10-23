from collections.abc import Generator

from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
)

from models._api import TokenerAPIModel


class TokenerText2SpeechModel(TokenerAPIModel, TTSModel):
    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: str | None = None,
    ) -> Generator[bytes, None, None]:
        if not content_text.strip():
            raise InvokeBadRequestError("Text-to-speech input must not be empty")
        if model not in {schema.model for schema in self.model_schemas}:
            raise InvokeBadRequestError("Text-to-speech model is not configured")
        voices = self.get_tts_model_voices(model, credentials) or []
        if voice not in {item["value"] for item in voices}:
            voice = self._get_model_default_voice(model, credentials)
        limit = self._get_model_word_limit(model, credentials)
        audio_format = self._get_model_audio_type(model, credentials)
        if audio_format not in ("mp3", "aac", "opus", "pcm"):
            raise InvokeBadRequestError("Audio format does not support sequential speech output")
        has_audio = False
        for sentence in self._split_text_into_sentences(content_text, max_length=limit):
            for start in range(0, len(sentence), limit):
                if not (text_chunk := sentence[start : start + limit].strip()):
                    continue
                with self._request(
                    "audio/speech",
                    credentials,
                    json={
                        "model": model,
                        "voice": voice,
                        "response_format": audio_format,
                        "input": text_chunk,
                    },
                    stream=True,
                    timeout=(10, 300),
                ) as response:
                    for audio_chunk in response.iter_content(chunk_size=1024):
                        if audio_chunk:
                            has_audio = True
                            yield audio_chunk
        if not has_audio:
            raise InvokeBadRequestError("No audio bytes found")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            for _ in self.invoke(model, "", credentials, "Hello Dify!", ""):
                pass
        except InvokeError as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex
