import base64
import json
import logging
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import IO, Any

import requests
from dashscope.audio.asr import Recognition, Transcription
from dashscope.utils.oss_utils import OssUtils
from dify_plugin import OAICompatSpeech2TextModel
from models._common import get_http_base_address, get_ws_base_address
from pydub import AudioSegment

from ..constant import BURY_POINT_HEADER

logger = logging.getLogger(__name__)

_AUDIO_MAGIC = [(0, b"fLaC", "flac"), (0, b"ID3", "mp3"), (0, b"#!AMR", "amr")]
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
_HTTP_TIMEOUT = (10, 600)
_RETRY_BACKOFFS = (1, 3)
_DASHSCOPE_ASYNC_BRIDGE_PATCHED = False
_FUN_ASR_MODEL = "fun-asr"
_FUN_ASR_FLASH_MODEL = "fun-asr-flash-2026-06-15"
_FUN_ASR_FLASH_MAX_FILE_SIZE = 7 * 1024 * 1024
_FUN_ASR_TASK_TIMEOUT = 3 * 60 * 60


def _is_subprocess_enabled() -> bool:
    value = os.getenv(_SUBPROCESS_ENV)
    return value is not None and value.strip().lower() in _SUBPROCESS_TRUE_VALUES


def _patch_dashscope_async_bridge_for_gevent() -> None:
    """Patch DashScope's global async bridge to use native threads under gevent.

    This replaces ``dashscope.common.utils.iter_over_async`` for the current
    plugin process. It affects all subsequent DashScope calls that use that
    helper, and is intentionally guarded so it is only applied once.
    """

    global _DASHSCOPE_ASYNC_BRIDGE_PATCHED
    if _DASHSCOPE_ASYNC_BRIDGE_PATCHED:
        return

    try:
        from gevent import monkey as gevent_monkey
    except ImportError:
        _DASHSCOPE_ASYNC_BRIDGE_PATCHED = True
        return
    except Exception as ex:
        logger.warning("DashScope async bridge patch skipped: failed to import gevent: %s", ex)
        _DASHSCOPE_ASYNC_BRIDGE_PATCHED = True
        return

    if not gevent_monkey.is_module_patched("threading"):
        _DASHSCOPE_ASYNC_BRIDGE_PATCHED = True
        return

    import asyncio
    import queue
    import threading

    try:
        import dashscope.common.utils as dashscope_utils
        from dashscope.api_entities.dashscope_response import DashScopeAPIResponse
        from dashscope.common.logging import logger as dashscope_logger
    except ImportError as ex:
        logger.warning("DashScope async bridge patch skipped: incompatible DashScope SDK: %s", ex)
        _DASHSCOPE_ASYNC_BRIDGE_PATCHED = True
        return
    except Exception as ex:
        logger.warning(
            "DashScope async bridge patch skipped: failed to import DashScope internals: %s", ex
        )
        _DASHSCOPE_ASYNC_BRIDGE_PATCHED = True
        return

    try:
        native_thread = gevent_monkey.get_original("threading", "Thread")
        native_queue = gevent_monkey.get_original("queue", "Queue")
    except Exception as ex:
        logger.warning(
            "DashScope async bridge patch falling back to current thread primitives: %s", ex
        )
        native_thread = threading.Thread
        native_queue = queue.Queue

    def iter_over_async_with_native_bridge(ait):
        loop = asyncio.new_event_loop()
        ait = ait.__aiter__()

        async def get_next():
            try:
                obj = await ait.__anext__()
                return False, obj
            except StopAsyncIteration:
                return True, None

        def iter_thread(loop, message_queue):
            asyncio.set_event_loop(loop)
            try:
                while True:
                    try:
                        done, obj = loop.run_until_complete(get_next())
                        if done:
                            message_queue.put((True, None, None))
                            break
                        message_queue.put((False, None, obj))
                    except BaseException as ex:
                        dashscope_logger.exception(ex)
                        message_queue.put((True, ex, None))
                        break
            finally:
                loop.close()

        message_queue = native_queue()
        worker = native_thread(
            target=iter_thread, args=(loop, message_queue), name="dashscope_iter_async_thread"
        )
        worker.daemon = True
        worker.start()
        while True:
            finished, error, obj = message_queue.get()
            if finished:
                if error is not None:
                    yield DashScopeAPIResponse(
                        -1, "", "Unknown", message=f"Error type: {type(error)}, message: {error}"
                    )
                break
            yield obj

    dashscope_utils.iter_over_async = iter_over_async_with_native_bridge
    _DASHSCOPE_ASYNC_BRIDGE_PATCHED = True


def _get_recognition_timeout() -> int:
    value = os.getenv(_RECOGNITION_TIMEOUT_ENV)
    if not value:
        return _DEFAULT_RECOGNITION_TIMEOUT
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_RECOGNITION_TIMEOUT
    return seconds if seconds > 0 else _DEFAULT_RECOGNITION_TIMEOUT


def _format_dashscope_error(status: Any, code: Any, message: Any, request_id: Any) -> str:
    return (
        f"DashScope error: {message or 'Unknown DashScope error'} "
        f"(status: {status or 'Unknown'}, code: {code or 'Unknown'}, "
        f"request_id: {request_id or 'Unknown'})"
    )


def _read_ebml_vint(data: bytes, offset: int) -> tuple[int, int] | None:
    if offset >= len(data) or data[offset] == 0:
        return None
    length = 1
    marker = 0x80
    while (data[offset] & marker) == 0:
        marker >>= 1
        length += 1
    if length > 8 or offset + length > len(data):
        return None
    value = data[offset] & (marker - 1)
    for byte in data[offset + 1 : offset + length]:
        value = (value << 8) | byte
    return value, length


def _get_ebml_format(data: bytes) -> str | None:
    header_size = _read_ebml_vint(data, 4)
    if header_size is None:
        return None
    size, size_length = header_size
    offset = 4 + size_length
    end = offset + size
    if end > len(data):
        return None
    while offset < end:
        element_start = offset
        element_id = _read_ebml_vint(data, offset)
        if element_id is None:
            return None
        _, id_length = element_id
        offset += id_length
        element_size = _read_ebml_vint(data, offset)
        if element_size is None:
            return None
        value_size, value_size_length = element_size
        offset += value_size_length
        value_end = offset + value_size
        if value_end > end:
            return None
        if data[element_start : element_start + id_length] == b"\x42\x82":
            doctype = data[offset:value_end].rstrip(b"\0")
            return {b"webm": "webm", b"matroska": "mkv"}.get(doctype)
        offset = value_end
    return None


def _parse_json_response(response) -> dict:
    try:
        data = response.json()
    except ValueError as ex:
        body = response.text[:500]
        headers = getattr(response, "headers", {}) or {}
        request_id = headers.get("x-request-id") or headers.get("x-oss-request-id")
        raise ValueError(
            _format_dashscope_error(response.status_code, "InvalidJSONResponse", body, request_id)
        ) from ex

    if not isinstance(data, dict):
        raise TypeError("DashScope returned invalid JSON: expected an object")
    if response.status_code != 200:
        headers = getattr(response, "headers", {}) or {}
        request_id = (
            data.get("request_id") or headers.get("x-request-id") or headers.get("x-oss-request-id")
        )
        raise ValueError(
            _format_dashscope_error(
                response.status_code,
                data.get("code"),
                data.get("message") or response.text,
                request_id,
            )
        )
    return data


def _raise_for_dashscope_error(response) -> None:
    if response.status_code != 200:
        raise ValueError(
            _format_dashscope_error(
                response.status_code,
                getattr(response, "code", None),
                getattr(response, "message", None),
                getattr(response, "request_id", None),
            )
        )


def _run_recognition_in_subprocess(
    file_path: str,
    model: str,
    audio_format: str,
    sample_rate: int,
    api_key: str,
    base_address: str | None,
    headers: dict,
    timeout: int | None = None,
) -> tuple[str, Any]:
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
        self, model: str, credentials: dict, file: IO[bytes], user: str | None = None
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
            file.seek(0)
            audio_format = self.get_audio_type(file)
            if audio_format == "unknown":
                raise ValueError("Unsupported audio format")
            file.seek(0)
            file_path = self.write_bytes_to_temp_file(file, audio_format)
            api_key = credentials["dashscope_api_key"]

            if model == _FUN_ASR_MODEL:
                return self._invoke_fun_asr(
                    model, file_path, api_key, get_http_base_address(credentials)
                )
            if model == _FUN_ASR_FLASH_MODEL:
                return self._invoke_fun_asr_flash(
                    model, file_path, audio_format, api_key, get_http_base_address(credentials)
                )

            audio = AudioSegment.from_file(file_path, format=audio_format)
            sample_rate = audio.frame_rate
            ws_base_address = get_ws_base_address(credentials)
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
                _patch_dashscope_async_bridge_for_gevent()
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
                _raise_for_dashscope_error(result)
                sentence_list = result.get_sentence()

            if not sentence_list:
                return ""
            sentence_ans = [
                sentence.get("text", "") if isinstance(sentence, dict) else str(sentence)
                for sentence in sentence_list
            ]
            return "\n".join(sentence_ans)
        except requests.exceptions.RequestException:
            raise
        except Exception as ex:
            raise ValueError(f"[TongyiSpeech2TextModel] {ex}") from ex
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

    def _invoke_fun_asr_flash(
        self, model: str, file_path: str, audio_format: str, api_key: str, base_address: str
    ) -> str:
        if os.path.getsize(file_path) > _FUN_ASR_FLASH_MAX_FILE_SIZE:
            raise ValueError("Fun-ASR-Flash audio must not exceed 7 MB before Base64 encoding")
        mime_type = (
            {"mp3": "audio/mpeg", "wav": "audio/wav"}.get(audio_format)
            or mimetypes.guess_type(file_path)[0]
            or "application/octet-stream"
        )
        audio_data = base64.b64encode(Path(file_path).read_bytes()).decode()
        response = requests.post(
            f"{base_address}/services/aigc/multimodal-generation/generation",
            headers={
                **BURY_POINT_HEADER,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-DashScope-SSE": "disable",
            },
            json={
                "model": model,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": f"data:{mime_type};base64,{audio_data}"
                                    },
                                }
                            ],
                        }
                    ]
                },
                "parameters": {"format": audio_format},
            },
            timeout=_HTTP_TIMEOUT,
        )
        data = _parse_json_response(response)
        text = (data.get("output") or {}).get("text")
        if not isinstance(text, str):
            raise TypeError(
                "DashScope returned an invalid Fun-ASR-Flash response: missing output.text"
            )
        return text

    def _invoke_fun_asr(self, model: str, file_path: str, api_key: str, base_address: str) -> str:
        # ponytail: official temporary uploads are non-production; accept a stable
        # public URL before adding OSS credentials to this byte-only Dify interface.
        oss_url, _ = OssUtils.upload(
            model=model,
            file_path=file_path,
            api_key=api_key,
            base_address=base_address,
            headers=BURY_POINT_HEADER,
        )
        submit_data = _parse_json_response(
            requests.post(
                f"{base_address}/services/audio/asr/transcription",
                headers={
                    **BURY_POINT_HEADER,
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                    "X-DashScope-OssResourceResolve": "enable",
                },
                json={"model": model, "input": {"file_urls": [oss_url]}, "parameters": {}},
                timeout=_HTTP_TIMEOUT,
            )
        )
        task_id = (submit_data.get("output") or {}).get("task_id")
        if not task_id:
            raise ValueError("DashScope returned an invalid Fun-ASR response: missing task_id")

        deadline = time.monotonic() + _FUN_ASR_TASK_TIMEOUT
        for backoff in (*_RETRY_BACKOFFS, None):
            try:
                task_response = Transcription.wait(
                    task_id,
                    api_key=api_key,
                    base_address=base_address,
                    headers=BURY_POINT_HEADER,
                    wait_timeout=max(1, deadline - time.monotonic()),
                )
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if backoff is None or time.monotonic() + backoff >= deadline:
                    raise
                time.sleep(backoff)
        _raise_for_dashscope_error(task_response)
        output = task_response.output or {}
        task_status = output.get("task_status")

        results = output.get("results") or []
        result = results[0] if results else {}
        if result.get("subtask_status") != "SUCCEEDED":
            code = result.get("code") or output.get("code") or task_status or "Unknown"
            message = (
                result.get("message") or output.get("message") or "Fun-ASR transcription failed"
            )
            raise ValueError(
                _format_dashscope_error(
                    result.get("subtask_status") or task_status,
                    code,
                    message,
                    task_response.request_id,
                )
            )

        transcription_url = result.get("transcription_url")
        if not transcription_url:
            raise ValueError(
                "DashScope returned an invalid Fun-ASR response: missing transcription_url"
            )
        for backoff in (*_RETRY_BACKOFFS, None):
            try:
                result_response = requests.get(transcription_url, timeout=_HTTP_TIMEOUT)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if backoff is None:
                    raise
            else:
                if result_response.status_code < 500 or backoff is None:
                    break
            if backoff is not None:
                time.sleep(backoff)
        transcription = _parse_json_response(result_response)
        transcripts = transcription.get("transcripts")
        if not isinstance(transcripts, list):
            raise TypeError("DashScope returned an invalid Fun-ASR result: missing transcripts")

        texts = []
        for transcript in transcripts:
            text = transcript.get("text") if isinstance(transcript, dict) else None
            if not isinstance(text, str):
                raise TypeError("DashScope returned an invalid Fun-ASR transcript")
            if text:
                texts.append(text)
        return "\n".join(texts)

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
            header = file_obj.read(65536)
            if len(header) >= 12 and header[0:4] == b"RIFF":
                for (offset, signature), format_name in _RIFF_SUBTYPE.items():
                    if header[offset : offset + len(signature)] == signature:
                        return format_name
            if header.startswith(b"OggS"):
                page_segments = header[26] if len(header) > 26 else 0
                packet_start = 27 + page_segments
                return "opus" if header[packet_start : packet_start + 8] == b"OpusHead" else "ogg"
            if header.startswith(b"\x1a\x45\xdf\xa3"):
                ebml_format = _get_ebml_format(header)
                if ebml_format:
                    return ebml_format
            if header[4:8] == b"ftyp":
                brand_offset = 16 if header[:4] == b"\0\0\0\1" else 8
                if len(header) >= brand_offset + 8:
                    brand = header[brand_offset : brand_offset + 4]
                    if brand == b"qt  ":
                        return "mov"
                    if brand in {b"M4A ", b"M4B ", b"M4P "}:
                        return "m4a"
                    name = str(getattr(file_obj, "name", "") or "")
                    suffix = Path(name).suffix.removeprefix(".").lower()
                    if suffix in {"m4a", "mp4"}:
                        return suffix
                    return "mp4"
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
