import requests

from collections.abc import Generator

from dify_plugin import OAICompatText2SpeechModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
)

# Gandr /v1/audio/speech contract (inherited from the OpenAI speech API):
#   * model  -> pass "tts-1"
#   * input  -> the text
#   * voice  -> OpenAI voice names are accepted and mapped to Gandr engine
#               voices (see VOICE_ALIASES); gandr-* ids pass through.
#   * response_format -> "wav" (RIFF header) or "pcm" (headerless). There is
#               no mp3 encoder on the doors, so an mp3 request returns a
#               deliberate 400. The model yaml pins audio_type to wav.
#   * speed  -> sent through and clamped by the Gandr shim to 0.6 ... 1.5.
#
# Request shape is OpenAI's, so an unmodified OpenAI client pointed at the
# Gandr base URL gets audio without any code change.

VOICE_ALIASES = {
    "alloy": "gandr-mia",
    "ash": "gandr-dane",
    "onyx": "gandr-dane",
    "ballad": "gandr-lewis",
    "fable": "gandr-lewis",
    "coral": "gandr-ava",
    "sage": "gandr-ava",
    "shimmer": "gandr-ava",
    "echo": "gandr-leo",
    "verse": "gandr-leo",
    "nova": "gandr-jenny",
}

_AUDIO_FORMATS = ("wav", "pcm")


class GandrText2SpeechModel(OAICompatText2SpeechModel):
    """Gandr TTS model mapped onto an OpenAI-compatible speech endpoint.

    Maps OpenAI-style params (voice, response_format, speed) to the Gandr
    OpenAI-compatible endpoint, streams audio back per sentence, and raises
    the plugin's Invoke* exceptions on failures.
    """

    def get_tts_model_voices(
        self, model: str, credentials: dict, language: str | None = None
    ) -> list | None:
        """Return the voice names a caller may pick.

        Both OpenAI names and the gandr-* engine ids are accepted by the
        endpoint, so both are offered. The OpenAI names are mapped server-side
        so an OpenAI client always receives audio.
        """
        del language
        values = list(VOICE_ALIASES) + list(VOICE_ALIASES.values())
        voices = [
            {
                "name": value if value.startswith("gandr-") else f"{value} ({VOICE_ALIASES[value]})",
                "value": value,
            }
            for value in values
        ]
        seen, deduped = set(), []
        for v in voices:
            if v["value"] not in seen:
                seen.add(v["value"])
                deduped.append(v)
        return deduped

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            voice = self._get_model_default_voice(model, credentials) or "alloy"
            next(
                self._invoke(
                    model=model,
                    tenant_id="validate",
                    credentials=credentials,
                    content_text="Hello from Gandr.",
                    voice=voice,
                )
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

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

        response_format = self._get_model_audio_type(model, credentials) or "wav"
        if response_format not in _AUDIO_FORMATS:
            raise InvokeBadRequestError(
                "Gandr supports response_format \"wav\" or \"pcm\", "
                f"got {response_format!r}"
            )

        gandr_voice = VOICE_ALIASES.get(voice, voice)
        if not gandr_voice.startswith("gandr-") and gandr_voice not in VOICE_ALIASES:
            gandr_voice = (
                self._get_model_default_voice(model, credentials) or "alloy"
            )

        base_url = (credentials.get("api_base") or "https://tts.gandr.ai").rstrip("/")
        endpoint_url = f"{base_url}/v1/audio/speech"
        word_limit = self._get_model_word_limit(model, credentials) or 500

        return self._stream_speech(
            endpoint_url=endpoint_url,
            api_key=credentials.get("api_key", ""),
            content_text=content_text,
            voice=gandr_voice,
            response_format=response_format,
            speed=credentials.get("speed"),
            word_limit=word_limit,
        )

    def _stream_speech(
        self,
        endpoint_url: str,
        api_key: str,
        content_text: str,
        voice: str,
        response_format: str,
        speed: float | str | None,
        word_limit: int,
    ) -> Generator[bytes, None, None]:
        """POST each sentence to the Gandr OpenAI-compatible speech endpoint.

        Streaming mirrors the upstream OpenAI-compatible base class: one
        request per sentence, yielding raw audio bytes. Non-200 responses
        raise InvokeBadRequestError; transport-level errors are left for the
        base error mapping to classify.
        """
        headers = {"Authorization": f"Bearer {api_key}"}
        sentences = self._split_text_into_sentences(content_text, max_length=word_limit)

        for sentence in sentences:
            payload = {
                "model": "tts-1",
                "input": sentence,
                "voice": voice,
                "response_format": response_format,
            }
            if speed not in (None, "", 1, 1.0):
                try:
                    payload["speed"] = float(speed)
                except (TypeError, ValueError):
                    raise InvokeBadRequestError(f"Invalid speed: {speed!r}")

            response = requests.post(
                endpoint_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=(10, 300),
            )
            if response.status_code != 200:
                raise InvokeBadRequestError(
                    f"Gandr speech request failed (HTTP {response.status_code}): "
                    f"{response.text[:500]}"
                )
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk

