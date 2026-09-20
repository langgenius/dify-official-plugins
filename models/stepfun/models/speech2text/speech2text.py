import base64
from typing import IO

from dify_plugin import Speech2TextModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeServerUnavailableError,
)

from .._audio import StepAudioTransport


class StepfunSpeech2TextModel(StepAudioTransport, Speech2TextModel):
    _MAX_BYTES = 25 * 1024 * 1024

    def _invoke(
        self, model: str, credentials: dict, file: IO[bytes], user: str | None = None
    ) -> str:
        audio = file.read(self._MAX_BYTES + 1)
        if not audio or len(audio) > self._MAX_BYTES:
            raise InvokeBadRequestError("Audio must be non-empty and no larger than 25 MiB")
        audio_format = self._audio_format(audio)
        payload = {
            "audio": {
                "data": base64.b64encode(audio).decode("ascii"),
                "input": {
                    "transcription": {"model": model, "enable_itn": True},
                    "format": {"type": audio_format},
                },
            }
        }
        with self._post_audio(
            credentials, "audio/asr/sse", payload, "text/event-stream"
        ) as response:
            for event in self._events(response):
                if event.get("type") == "error" or event.get("error"):
                    raise InvokeServerUnavailableError(
                        f"StepFun ASR failed: {event.get('message', 'upstream error')}"
                    )
                if event.get("type") == "transcript.text.done":
                    text = event.get("text")
                    if not isinstance(text, str):
                        raise InvokeServerUnavailableError(
                            "StepFun ASR returned invalid final text"
                        )
                    return text
        # Never return partial deltas as a successful transcription.
        raise InvokeServerUnavailableError("StepFun ASR ended without a final transcript")

    @staticmethod
    def _audio_format(audio: bytes) -> str:
        # Dify may pass an unnamed BytesIO: use the container signature, not a filename.
        if audio.startswith(b"RIFF") and audio[8:12] == b"WAVE":
            return "wav"
        if audio.startswith(b"OggS"):
            return "ogg"
        if audio[4:8] == b"ftyp":
            return "m4a"
        if audio.startswith(b"ID3") or (
            len(audio) > 1 and audio[0] == 0xFF and audio[1] & 0xE6 == 0xE2
        ):
            return "mp3"
        raise InvokeBadRequestError("Supported audio containers: WAV, MP3, OGG, M4A")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            with open(self._get_demo_file_path(), "rb") as file:
                self._invoke(model, credentials, file)
        except Exception as error:
            raise CredentialsValidateFailedError(str(error)) from error
