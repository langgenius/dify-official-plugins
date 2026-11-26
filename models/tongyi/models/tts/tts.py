import io
import re
import threading
import wave
from queue import Queue
from typing import Any
from urllib.request import urlopen

import requests
from dashscope import MultiModalConversation
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
)
from dify_plugin.interfaces.model.tts_model import TTSModel
from models._common import _CommonTongyi, get_http_base_address

from ..constant import BURY_POINT_HEADER

# DashScope writes int32 placeholder sizes into the RIFF and data chunk headers of
# its streaming WAVE output because the real length is unknown while the stream is
# still being written. Any declared size at or above this threshold is such a
# placeholder and must not be read as a truncation signal.
_STREAMING_WAV_PLACEHOLDER_BYTES = 0x7F000000


def _is_streaming_wav_placeholder(declared_bytes: int) -> bool:
    """Whether a WAVE size field belongs to DashScope's streaming placeholder family."""
    return declared_bytes >= _STREAMING_WAV_PLACEHOLDER_BYTES


def merge_wav_segments(segments: list[bytes]) -> bytes:
    """Join compatible PCM WAVE files into one valid WAVE container.

    DashScope returns one standalone WAVE file for each sentence when input is
    split at the provider word limit. Concatenating those containers produces a
    corrupt file; rebuilding one header around the combined PCM frames keeps
    long TTS output playable by browsers and API consumers.

    DashScope streams those WAVE containers with int32 placeholder sizes in the
    RIFF and data headers, so the declared frame count is meaningless; frames are
    taken from the bytes actually present in each segment.
    """
    if not segments:
        raise InvokeBadRequestError("No audio data returned by DashScope")

    output = io.BytesIO()
    expected_format: tuple[int, int, int, str] | None = None
    try:
        with wave.open(output, "wb") as writer:
            for index, segment in enumerate(segments, start=1):
                with wave.open(io.BytesIO(segment), "rb") as reader:
                    format_ = (
                        reader.getnchannels(),
                        reader.getsampwidth(),
                        reader.getframerate(),
                        reader.getcomptype(),
                    )
                    if format_[3] != "NONE":
                        raise InvokeBadRequestError(
                            f"DashScope returned unsupported compressed WAVE segment {index}"
                        )
                    if expected_format is None:
                        expected_format = format_
                        writer.setnchannels(format_[0])
                        writer.setsampwidth(format_[1])
                        writer.setframerate(format_[2])
                        writer.setcomptype(format_[3], "not compressed")
                    elif format_ != expected_format:
                        raise InvokeBadRequestError(
                            "DashScope returned WAVE segments with incompatible audio formats"
                        )

                    frame_count = reader.getnframes()
                    frames = reader.readframes(frame_count)
                    expected_frame_bytes = (
                        frame_count * reader.getnchannels() * reader.getsampwidth()
                    )
                    if len(frames) != expected_frame_bytes:
                        if not _is_streaming_wav_placeholder(expected_frame_bytes):
                            raise InvokeBadRequestError(
                                f"DashScope returned truncated WAVE segment {index}"
                            )
                        # The declared length is a streaming placeholder, so the payload
                        # length is the truth; drop a trailing partial frame if any.
                        block_align = reader.getnchannels() * reader.getsampwidth()
                        frames = frames[: len(frames) - len(frames) % block_align]
                        if not frames:
                            raise InvokeBadRequestError(
                                f"DashScope returned truncated WAVE segment {index}"
                            )
                    writer.writeframes(frames)
    except (EOFError, wave.Error) as ex:
        raise InvokeBadRequestError(f"DashScope returned an invalid WAVE segment: {ex}") from ex

    return output.getvalue()


_CUSTOM_MODEL_VOICES = (
    "Cherry",
    "Serena",
    "Ethan",
    "Chelsie",
    "Momo",
    "Vivian",
    "Moon",
    "Maia",
    "Kai",
    "Nofish",
)

# Qwen-Audio-TTS models use the SpeechSynthesizer HTTP API and their own voice IDs;
# voices cannot be shared with qwen3-tts models.
_QWEN_AUDIO_TTS_PATTERN = re.compile(r"qwen-audio-[\d.]+-tts-[a-z]+")
_QWEN_AUDIO_31_TTS_VOICES = (
    ("longanlingxin_v3.1", "龙安灵心"),
    ("xunanchuan_v3.1", "许南川"),
    ("longanhuan_v3.1", "龙安欢"),
    ("longanfengyue_v3.1", "龙安风悦"),
)
_HTTP_TIMEOUT = (10, 120)


def _custom_model_voices(model: str) -> list[tuple[str, str]]:
    if model.startswith("qwen-audio-3.1-tts-"):
        return list(_QWEN_AUDIO_31_TTS_VOICES)
    return [(voice, voice) for voice in _CUSTOM_MODEL_VOICES]


def _synthesize_qwen_audio(
    text: str, model: str, voice: str, api_key: str, base_address: str
) -> bytes:
    response = requests.post(
        f"{base_address}/services/audio/tts/SpeechSynthesizer",
        headers={
            **BURY_POINT_HEADER,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "input": {"text": text, "voice": voice, "format": "wav"}},
        timeout=_HTTP_TIMEOUT,
    )
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200:
        raise InvokeBadRequestError(
            f"DashScope error: {data.get('message') or response.text[:500]} "
            f"(status: {response.status_code}, code: {data.get('code')}, "
            f"request_id: {data.get('request_id')})"
        )
    audio_url = ((data.get("output") or {}).get("audio") or {}).get("url")
    if not audio_url:
        raise InvokeBadRequestError("No audio URL in response")
    audio_response = requests.get(audio_url, timeout=_HTTP_TIMEOUT)
    audio_response.raise_for_status()
    return audio_response.content


class TongyiText2SpeechModel(_CommonTongyi, TTSModel):
    """
    Model class for Tongyi Speech to text model.
    """

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        """Schema for user-added TTS models so they show up in model lists."""
        voices = _custom_model_voices(model)
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.TTS,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.DEFAULT_VOICE: voices[0][0],
                ModelPropertyKey.VOICES: [
                    {"mode": voice, "name": name, "language": ["zh-Hans", "en-US"]}
                    for voice, name in voices
                ],
                ModelPropertyKey.WORD_LIMIT: 512,
                ModelPropertyKey.AUDIO_TYPE: "wav",
                ModelPropertyKey.MAX_WORKERS: 5,
            },
        )

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: str | None = None,
    ) -> Any:
        """
        _invoke text2speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param voice: model timbre
        :param content_text: text content to be translated
        :param user: unique user id
        :return: text translated to audio file
        """
        if not voice or voice not in [
            d["value"] for d in self.get_tts_model_voices(model=model, credentials=credentials)
        ]:
            voice = self._get_model_default_voice(model, credentials)
        return self._tts_invoke_streaming(
            model=model, credentials=credentials, content_text=content_text, voice=voice
        )

    def validate_credentials(self, model: str, credentials: dict, user: str | None = None) -> None:
        """
        validate credentials text2speech model

        :param model: model name
        :param credentials: model credentials
        :param user: unique user id
        :return: text translated to audio file
        """
        try:
            # _tts_invoke_streaming is a generator; consume it so the API is actually called.
            for _ in self._tts_invoke_streaming(
                model=model,
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            ):
                pass
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> Any:
        """
        _tts_invoke_streaming text2speech model

        :param model: model name
        :param credentials: model credentials
        :param voice: model timbre
        :param content_text: text content to be translated
        :return: text translated to audio file
        """
        word_limit = self._get_model_word_limit(model, credentials)
        http_base_address = get_http_base_address(credentials)
        try:
            audio_queue: Queue = Queue()
            error_queue: Queue = Queue()

            def invoke_remote(content, m, api_key, wl, base_address):
                try:
                    audio_segments: list[bytes] = []
                    if len(content) < wl:
                        sentences = [content]
                    else:
                        sentences = list(
                            self._split_text_into_sentences(org_text=content, max_length=wl)
                        )
                    for sentence in sentences:
                        if _QWEN_AUDIO_TTS_PATTERN.fullmatch(m):
                            audio_segments.append(
                                _synthesize_qwen_audio(
                                    sentence.strip(), m, voice, api_key, base_address
                                )
                            )
                            continue
                        response_stream = MultiModalConversation.call(
                            model=m,
                            api_key=api_key,
                            text=sentence.strip(),
                            voice=voice,
                            stream=True,
                            base_address=base_address,
                        )
                        audio_url: str | None = None
                        for chunk in response_stream:
                            if chunk.status_code != 200:
                                error_msg = chunk.message or f"API error: {chunk.status_code}"
                                error_queue.put(InvokeBadRequestError(error_msg))
                                audio_queue.put(None)
                                return
                            audio = getattr(getattr(chunk, "output", None), "audio", None)
                            if audio:
                                audio_url = audio.get("url") or audio_url
                        if not audio_url:
                            error_queue.put(InvokeBadRequestError("No audio URL in response"))
                            audio_queue.put(None)
                            return
                        try:
                            with urlopen(audio_url, timeout=30) as response:
                                audio_data = response.read()
                            audio_segments.append(audio_data)
                        except Exception as e:
                            error_queue.put(
                                InvokeBadRequestError(f"Failed to download audio: {e!s}")
                            )
                            audio_queue.put(None)
                            return
                    audio_queue.put(merge_wav_segments(audio_segments))
                    audio_queue.put(None)
                except Exception as e:
                    error_queue.put(self._map_invoke_error(e))
                    audio_queue.put(None)

            threading.Thread(
                target=invoke_remote,
                args=(
                    content_text,
                    model,
                    credentials.get("dashscope_api_key"),
                    word_limit,
                    http_base_address,
                ),
                daemon=True,
            ).start()
            while True:
                audio = audio_queue.get()
                if audio is None:
                    if not error_queue.empty():
                        error = error_queue.get()
                        if error:
                            raise error
                    break
                yield audio
        except InvokeError:
            raise
        except Exception as ex:
            raise InvokeBadRequestError(str(ex))

    def _map_invoke_error(self, error: Exception) -> InvokeError:
        error_mapping = self._invoke_error_mapping
        for invoke_error_type, dashscope_errors in error_mapping.items():
            if isinstance(error, tuple(dashscope_errors)):
                return invoke_error_type(str(error))
        return InvokeBadRequestError(str(error))
