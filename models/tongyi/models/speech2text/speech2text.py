import os
import tempfile
import uuid
from typing import IO, Optional

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
            recognition = Recognition(
                model=str(model),
                format=str(audio_format),
                sample_rate=int(sample_rate),
                callback=None,
            )
            result = recognition.call(
                file=file_path,
                headers=BURY_POINT_HEADER,
                api_key=credentials["dashscope_api_key"],
                base_address=ws_base_address,
            )
            sentence_list = result.get_sentence()
            if sentence_list is None:
                return ""
            else:
                sentence_ans = []
                for sentence in sentence_list:
                    sentence_ans.append(sentence["text"])
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
