import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import IO, Any, Optional, Tuple

from dashscope.audio.asr import Recognition
from dify_plugin import OAICompatSpeech2TextModel
from models._common import get_ws_base_address
from pydub import AudioSegment

from ..constant import BURY_POINT_HEADER

_AUDIO_MAGIC = [
    (0, b"fLaC", "flac"),
    (0, b"ID3", "mp3"),
    (0, b"OggS", "ogg"),
    (0, b"\x1a\x45\xdf\xa3", "webm"),
    (4, b"ftyp", "m4a"),
    (0, b"#!AMR", "amr"),
]
_RIFF_SUBTYPE = {(8, b"WAVE"): "wav", (8, b"AVI "): "avi"}
_AUDIO_FORMATS_FALLBACK = [
    "wav",
    "mp3",
    "webm",
    "ogg",
    "m4a",
    "flac",
    "opus",
    "aac",
    "amr",
    "flv",
    "mkv",
    "mov",
    "mp4",
    "mpeg",
    "avi",
    "wma",
    "wmv",
]
_WORKER_SCRIPT_PATH = str(Path(__file__).resolve().parent / "_stt_worker.py")
_SUBPROCESS_ENV = "TONGYI_STT_SUBPROCESS"
_SUBPROCESS_TRUE_VALUES = {"1", "true", "yes", "on"}
_RECOGNITION_TIMEOUT_ENV = "TONGYI_STT_RECOGNITION_TIMEOUT"
_DEFAULT_RECOGNITION_TIMEOUT = 120


def _is_subprocess_enabled() -> bool:
    value = os.getenv(_SUBPROCESS_ENV)
    return value is not None and value.strip().lower() in _SUBPROCESS_TRUE_VALUES


def _get_recognition_timeout() -> int:
    value = os.getenv(_RECOGNITION_TIMEOUT_ENV)
    if not value:
        return _DEFAULT_RECOGNITION_TIMEOUT
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_RECOGNITION_TIMEOUT
    return seconds if seconds > 0 else _DEFAULT_RECOGNITION_TIMEOUT


def _run_recognition_in_subprocess(
    file_path: str,
    model: str,
    audio_format: str,
    sample_rate: int,
    api_key: str,
    base_address: Optional[str],
    headers: dict,
    timeout: Optional[int] = None,
) -> Tuple[str, Any]:
    if timeout is None:
        timeout = _get_recognition_timeout()

    args_json = json.dumps(
        {
            "file_path": file_path,
            "model": model,
            "audio_format": audio_format,
            "sample_rate": sample_rate,
            "api_key": api_key,
            "base_address": base_address,
            "headers": headers or {},
        }
    )
    try:
        proc = subprocess.Popen(
            [sys.executable, _WORKER_SCRIPT_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as ex:
        return ("err", f"spawn worker: {ex}")

    try:
        out, err = proc.communicate(input=args_json.encode(), timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return ("err", "speech recognition timed out")
    except Exception as ex:
        try:
            proc.kill()
        except Exception:
            pass
        return ("err", f"communicate: {ex}")

    if proc.returncode != 0:
        err_tail = (err.decode("utf-8", errors="replace") or out.decode("utf-8", errors="replace"))[
            -500:
        ]
        return ("err", f"worker exit {proc.returncode}: {err_tail}")

    try:
        result = json.loads(out.decode("utf-8").strip() or "{}")
    except Exception as ex:
        return ("err", f"parse result: {ex}; out={out[:200]!r}")
    return (result.get("status", "err"), result.get("data"))


class TongyiSpeech2TextModel(OAICompatSpeech2TextModel):
    """
    Model class for Tongyi Speech to text model.
    """

    def _invoke(
        self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None
    ) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        file_path = None
        try:
            ws_base_address = get_ws_base_address(credentials)
            file.seek(0)
            audio_format = self.get_audio_type(file)
            if audio_format == "unknown":
                raise ValueError("Unsupported audio format")
            audio = AudioSegment.from_file(file, format=audio_format)
            sample_rate = audio.frame_rate
            file.seek(0)
            file_path = self.write_bytes_to_temp_file(file, audio_format)
            api_key = credentials["dashscope_api_key"]

            if _is_subprocess_enabled():
                headers = dict(BURY_POINT_HEADER) if BURY_POINT_HEADER else {}
                status, data = _run_recognition_in_subprocess(
                    file_path,
                    str(model),
                    audio_format,
                    int(sample_rate),
                    api_key,
                    ws_base_address,
                    headers,
                )
                if status == "err":
                    raise ValueError(data or "Unknown error in STT worker subprocess")
                sentence_list = data
            else:
                recognition = Recognition(
                    model=str(model),
                    format=str(audio_format),
                    sample_rate=int(sample_rate),
                    callback=None,
                )
                result = recognition.call(
                    file=file_path,
                    headers=BURY_POINT_HEADER,
                    api_key=api_key,
                    base_address=ws_base_address,
                )
                sentence_list = result.get_sentence()

            if not sentence_list:
                return ""
            sentence_ans = [
                sentence.get("text", "") if isinstance(sentence, dict) else str(sentence)
                for sentence in sentence_list
            ]
            return "\n".join(sentence_ans)
        except Exception as ex:
            raise ValueError(f"[TongyiSpeech2TextModel] {ex}") from ex
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

    def write_bytes_to_temp_file(self, file: IO[bytes], file_extension: str) -> str:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f"{uuid.uuid4()}_audio.{file_extension}")
        with open(file_path, "wb") as temp_file:
            file_content = file.read()
            if not file_content:
                raise ValueError("The audio file is empty")
            temp_file.write(file_content)
        return file_path

    def get_audio_type(self, file_obj: IO[bytes]) -> str:
        current_position = file_obj.tell()
        file_obj.seek(0)
        try:
            header = file_obj.read(12)
            if len(header) >= 12 and header[0:4] == b"RIFF":
                for (offset, signature), format_name in _RIFF_SUBTYPE.items():
                    if header[offset : offset + len(signature)] == signature:
                        return format_name
            for offset, signature, format_name in _AUDIO_MAGIC:
                if (
                    len(header) >= offset + len(signature)
                    and header[offset : offset + len(signature)] == signature
                ):
                    return format_name
            detected_format = "unknown"
            for format_name in _AUDIO_FORMATS_FALLBACK:
                try:
                    file_obj.seek(0)
                    AudioSegment.from_file(file_obj, format=format_name)
                    detected_format = format_name
                    break
                except Exception:
                    continue
            return detected_format
        finally:
            file_obj.seek(current_position)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        return super().validate_credentials(model, credentials)
