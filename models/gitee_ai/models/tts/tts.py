from collections.abc import Generator
from io import BytesIO
from typing import Optional

import requests
from pydub import AudioSegment

from .._common import _CommonGiteeAI
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError
from dify_plugin.interfaces.model.tts_model import TTSModel


class GiteeAIText2SpeechModel(_CommonGiteeAI, TTSModel):
    """
    Model class for GiteeAI Speech to text model.
    """

    def _invoke(
        self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str, user: Optional[str] = None
    ) -> any:
        """
        _invoke text2speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :param user: unique user id
        :return: text translated to audio file
        """
        return self._tts_invoke_streaming(model=model, credentials=credentials, content_text=content_text, voice=voice)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        validate credentials text2speech model

        :param model: model name
        :param credentials: model credentials
        :return: text translated to audio file
        """
        try:
            audio_data = b''.join(self._tts_invoke_streaming(
                model=model,
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            ))
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke_streaming(self, model: str, credentials: dict, content_text: str, voice: str) -> Generator[bytes, None, None]:
        """
        _tts_invoke_streaming text2speech model
        :param model: model name
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :return: text translated to audio file
        """
        try:
            endpoint_url = "https://ai.gitee.com/v1/audio/speech"
            headers = {"Content-Type": "application/json"}
            api_key = credentials.get("api_key")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "model": model,
                "input": content_text
            }
            with requests.post(endpoint_url, headers=headers, json=payload, stream=True) as response:
                if response.status_code != 200:
                    raise InvokeBadRequestError(response.text)
                # 收集所有wav流
                wav_bytes = b""
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        wav_bytes += chunk
                try:
                    # 用pydub转为mp3
                    audio = AudioSegment.from_file(BytesIO(wav_bytes), format="wav")
                    buffer = BytesIO()
                    audio.export(buffer, format="mp3")
                    buffer.seek(0)
                    # 流式输出mp3
                    chunk_size = 1024
                    while True:
                        chunk = buffer.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
                except Exception as trans_ex:
                    # 兼容mp3流
                    yield wav_bytes
        except Exception as ex:
            raise InvokeBadRequestError(str(ex))
