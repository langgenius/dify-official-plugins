from collections.abc import Generator

from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
)

from .._audio import StepAudioTransport


class StepfunText2SpeechModel(StepAudioTransport, TTSModel):
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
        voices = self.get_tts_model_voices(model, credentials) or []
        if not voices:
            raise InvokeBadRequestError("No voices found for the model")
        if voice not in {item["value"] for item in voices}:
            voice = self._get_model_default_voice(model, credentials) or voices[0]["value"]
        return self._tts_invoke_streaming(model, credentials, content_text, voice)

    def _tts_invoke_streaming(self, model, credentials, content_text, voice):
        # Follow OpenAI's sentence splitting, with StepFun's 1000-character limit.
        limit = min(self._get_model_word_limit(model, credentials) or 1000, 1000)
        for sentence in self._split_text_into_sentences(content_text, max_length=limit):
            for start in range(0, len(sentence), limit):
                if text := sentence[start : start + limit].strip():
                    yield from self._audio_stream(
                        credentials,
                        {
                            "model": model,
                            "input": text,
                            "voice": voice,
                            "response_format": "mp3",
                            "stream_format": "audio",
                        },
                    )

    def validate_credentials(self, model: str, credentials: dict, user: str | None = None):
        try:
            # Consume the generator to validate the actual synthesis request.
            for _ in self._invoke(model, "", credentials, "Hello Dify!", "", user):
                pass
        except Exception as error:
            raise CredentialsValidateFailedError(str(error)) from error
