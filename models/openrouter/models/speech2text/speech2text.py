import base64
from typing import IO

from dify_plugin import Speech2TextModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
    InvokeServerUnavailableError,
)

from models._audio_utils import build_headers, post
from models._endpoint_utils import normalize_endpoint_url


def detect_audio_format(header: bytes) -> str:
    """Return the OpenRouter `input_audio.format` for an audio file header.

    Dify hands the plugin an anonymous temporary file, so the container has to be
    recognised from its magic bytes; MP3 is the fallback, as in the Dify SDK.
    """
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if header[4:8] == b"ftyp":
        return "m4a"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if header[:2] in (b"\xff\xf1", b"\xff\xf9"):
        return "aac"
    return "mp3"


class OpenRouterSpeech2TextModel(Speech2TextModel):
    """Speech-to-text models served through OpenRouter's /audio/transcriptions API."""

    def _invoke(
        self, model: str, credentials: dict, file: IO[bytes], user: str | None = None
    ) -> str:
        del user
        return self._speech2text_invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            with open(self._get_demo_file_path(), "rb") as audio_file:
                self._speech2text_invoke(model, credentials, audio_file)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def _speech2text_invoke(self, model: str, credentials: dict, file: IO[bytes]) -> str:
        audio = file.read()
        if not audio:
            raise InvokeBadRequestError("Audio file must not be empty")

        payload = {
            "model": model,
            "input_audio": {
                "data": base64.b64encode(audio).decode("ascii"),
                "format": detect_audio_format(audio[:16]),
            },
        }
        response = post(
            f"{normalize_endpoint_url(credentials)}/audio/transcriptions",
            "speech-to-text",
            headers=build_headers(credentials),
            json=payload,
        )
        try:
            text = response.json()["text"]
        except (ValueError, KeyError, TypeError) as ex:
            raise InvokeServerUnavailableError(
                f"OpenRouter returned an invalid transcription response: {ex}"
            ) from ex
        if not isinstance(text, str):
            raise InvokeServerUnavailableError("OpenRouter returned a non-text transcription.")
        return text

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {}
