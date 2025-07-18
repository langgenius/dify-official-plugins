import os
import uuid
from pydub import AudioSegment
import tempfile
from typing import IO, Optional
import dashscope
from dify_plugin import OAICompatSpeech2TextModel
from dashscope.audio.asr import *

class TongyiSpeech2TextModel(OAICompatSpeech2TextModel):
    """
    Model class for Tongyi Speech to text model.
    """

    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        try:
            dashscope.api_key = credentials["dashscope_api_key"]
            file.seek(0)
            audio = AudioSegment.from_file(file)
            sample_rate = audio.frame_rate
            file.seek(0)
            audio_format = self.get_audio_type(file)
            if audio_format == 'unknown':
                raise ValueError("Unsupported audio format")
            file.seek(0)
            file_path = self.write_bytes_to_temp_file(file, audio_format)
            recognition = Recognition(
                model=str(model),
                format=str(audio_format),
                sample_rate=int(sample_rate),
                callback=None,
            )
            result = recognition.call(file_path)
            sentence_list = result.get_sentence()
            if sentence_list is None:
                return ''
            else:
                sentence_ans = []
                for sentence in sentence_list:
                    sentence_ans.append(sentence['text'])
                return "\n".join(sentence_ans)
        except Exception as ex:
            raise ValueError(
                f"[TongyiSpeech2TextModel] {ex}"
            ) from ex
        
    def write_bytes_to_temp_file(self, file: IO[bytes], file_extension: str) -> str:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f"{uuid.uuid4()}_audio.{file_extension}")
        with open(file_path, "wb") as temp_file:
            file_content = file.read()
            if not file_content:
                raise ValueError("The audio file is empty")
            temp_file.write(file_content)
        return file_path

    def get_audio_type(self,file_obj: IO[bytes]) -> str:
        current_position = file_obj.tell()
        file_obj.seek(0)
        audio_formats = ['aac','amr','avi','flac','flv','m4a','mkv','mov','mp3','mp4','mpeg','ogg','opus','wav','webm','wma','wmv']
        detected_format = 'unknown'
        for format_name in audio_formats:
            try:
                file_obj.seek(0)
                AudioSegment.from_file(file_obj, format=format_name)
                detected_format = format_name
                break
            except Exception:
                continue
        file_obj.seek(current_position)
        return detected_format
    
    def validate_credentials(self, model: str, credentials: dict) -> None:
        return super().validate_credentials(model, credentials)
