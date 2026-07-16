from collections.abc import Generator

from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
)
from openai import OpenAI

from ..common_openai import _CommonOpenAI


class OpenAIText2SpeechModel(_CommonOpenAI, TTSModel):
    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: str | None = None,
    ) -> bytes | Generator[bytes, None, None]:
        if not content_text.strip():
            raise InvokeBadRequestError("Text-to-speech input must not be empty")

        voices = self.get_tts_model_voices(model=model, credentials=credentials)
        if not voices:
            raise InvokeBadRequestError("No voices found for the model")

        valid_voices = {item["value"] for item in voices}
        if voice not in valid_voices:
            voice = (
                self._get_model_default_voice(model, credentials) or voices[0]["value"]
            )

        return self._tts_invoke_streaming(
            model=model, credentials=credentials, content_text=content_text, voice=voice
        )

    def validate_credentials(
        self, model: str, credentials: dict, user: str | None = None
    ) -> None:
        try:
            self._tts_invoke(
                model=model,
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def _tts_invoke(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> bytes:
        client = OpenAI(**self._to_credential_kwargs(credentials))
        audio_type = self._get_model_audio_type(model, credentials) or "mp3"
        audio = bytearray()
        for sentence in self._sentences(model, credentials, content_text):
            response = client.audio.speech.create(
                model=model,
                voice=voice,
                response_format=audio_type,
                input=sentence,
            )
            audio.extend(response.read())

        if not audio:
            raise InvokeBadRequestError("No audio bytes found")
        return bytes(audio)

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> Generator[bytes, None, None]:
        client = OpenAI(**self._to_credential_kwargs(credentials))
        audio_type = self._get_model_audio_type(model, credentials) or "mp3"
        for sentence in self._sentences(model, credentials, content_text):
            with client.audio.speech.with_streaming_response.create(
                model=model,
                response_format=audio_type,
                input=sentence,
                voice=voice,
            ) as response:
                yield from response.iter_bytes(1024)

    def _sentences(
        self, model: str, credentials: dict, content_text: str
    ) -> Generator[str, None, None]:
        limit = self._get_model_word_limit(model, credentials) or 500
        for sentence in self._split_text_into_sentences(content_text, max_length=limit):
            for start in range(0, len(sentence), limit):
                if chunk := sentence[start : start + limit].strip():
                    yield chunk
