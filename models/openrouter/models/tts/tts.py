from collections.abc import Generator

from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
)

from models._audio_utils import build_headers, post
from models._endpoint_utils import normalize_endpoint_url

_CHUNK_SIZE = 4096


class OpenRouterText2SpeechModel(TTSModel):
    """Text-to-speech models served through OpenRouter's /audio/speech API."""

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: str | None = None,
    ) -> bytes | Generator[bytes, None, None]:
        del tenant_id, user
        if not content_text.strip():
            raise InvokeBadRequestError("Text-to-speech input must not be empty")

        voices = self.get_tts_model_voices(model=model, credentials=credentials) or []
        valid_voices = {item["value"] for item in voices}
        if valid_voices and voice not in valid_voices:
            voice = self._get_model_default_voice(model, credentials) or voices[0]["value"]

        return self._tts_invoke_streaming(model, credentials, content_text, voice)

    def validate_credentials(self, model: str, credentials: dict, user: str | None = None) -> None:
        del user
        try:
            audio = b"".join(
                self._tts_invoke_streaming(
                    model=model,
                    credentials=credentials,
                    content_text="Hello Dify!",
                    voice=self._get_model_default_voice(model, credentials),
                )
            )
            if not audio:
                raise InvokeBadRequestError("No audio bytes returned")
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str | None
    ) -> Generator[bytes, None, None]:
        url = f"{normalize_endpoint_url(credentials)}/audio/speech"
        headers = build_headers(credentials)
        audio_type = self._get_model_audio_type(model, credentials) or "mp3"
        for sentence in self._sentences(model, credentials, content_text):
            payload = {"model": model, "input": sentence, "response_format": audio_type}
            if voice:
                payload["voice"] = voice
            with post(
                url, "text-to-speech", headers=headers, json=payload, stream=True
            ) as response:
                yield from response.iter_content(chunk_size=_CHUNK_SIZE)

    def _sentences(
        self, model: str, credentials: dict, content_text: str
    ) -> Generator[str, None, None]:
        limit = self._get_model_word_limit(model, credentials) or 2000
        for sentence in self._split_text_into_sentences(content_text, max_length=limit):
            if chunk := sentence.strip():
                yield chunk

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {}
