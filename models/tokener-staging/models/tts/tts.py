import wave
from collections.abc import Generator
from contextlib import ExitStack, closing
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

import requests
from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeServerUnavailableError,
)

from models._api import TokenerAPIModel


def _merge_wav(segments: Generator[BinaryIO, None, None]) -> Generator[bytes, None, None]:
    with closing(segments), SpooledTemporaryFile(max_size=2**20) as output:
        try:
            with ExitStack() as stack:
                merged = None
                format_params = None
                for source in segments:
                    with wave.open(source, "rb") as wav:
                        params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
                        remaining = wav.getnframes()
                        if not remaining:
                            raise wave.Error("empty PCM data")
                        if merged is None:
                            merged = stack.enter_context(wave.open(output, "wb"))
                            merged.setnchannels(params[0])
                            merged.setsampwidth(params[1])
                            merged.setframerate(params[2])
                            format_params = params
                        elif params != format_params:
                            raise wave.Error("inconsistent PCM format")
                        while remaining:
                            frame_count = min(remaining, 4096)
                            frames = wav.readframes(frame_count)
                            if len(frames) != frame_count * params[0] * params[1]:
                                raise wave.Error("truncated PCM data")
                            merged.writeframesraw(frames)
                            remaining -= frame_count
        except (wave.Error, EOFError) as ex:
            raise InvokeServerUnavailableError("Tokener.ai returned invalid WAV audio") from ex
        if merged is None:
            raise InvokeBadRequestError("No audio bytes found")
        output.seek(0)
        while chunk := output.read(8192):
            yield chunk


def _read_audio(response: requests.Response, chunk_size: int) -> Generator[bytes, None, None]:
    try:
        yield from response.iter_content(chunk_size=chunk_size)
    except requests.RequestException as error:
        raise InvokeConnectionError("Unable to reach Tokener.ai") from error


def _wav_segments(
    responses: Generator[requests.Response, None, None], /
) -> Generator[BinaryIO, None, None]:
    with closing(responses):
        for response in responses:
            with SpooledTemporaryFile(max_size=2**20) as source:
                for chunk in _read_audio(response, 8192):
                    source.write(chunk)
                source.seek(0)
                yield source


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
        if audio_format not in ("mp3", "aac", "opus", "pcm", "wav"):
            raise InvokeBadRequestError("Audio format does not support sequential speech output")

        def responses() -> Generator[requests.Response, None, None]:
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
                        yield response

        if audio_format == "wav":
            yield from _merge_wav(_wav_segments(responses()))
            return
        has_audio = False
        with closing(responses()) as audio:
            for response in audio:
                for chunk in _read_audio(response, 1024):
                    if chunk:
                        has_audio = True
                        yield chunk
        if not has_audio:
            raise InvokeBadRequestError("No audio bytes found")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            for _ in self.invoke(model, "", credentials, "Hello Dify!", ""):
                pass
        except InvokeError as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex
