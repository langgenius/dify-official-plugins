import json
import logging
from abc import ABC
from collections.abc import Iterator
from typing import Any, Optional

import requests
from dify_plugin.entities.model import ModelPropertyKey
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.tts_model import TTSModel

logger = logging.getLogger(__name__)


class MinimaxText2SpeechModel(TTSModel, ABC):
    """
    Minimax Text-to-Speech Model
    """

    def validate_credentials(self, model: str, credentials: dict, user: Optional[str] = None) -> None:
        """
        validate credentials text2speech model

        :param model: model name
        :param credentials: model credentials
        :param user: unique user id
        :return: text translated to audio file
        """
        try:
            self._invoke(
                model=model,
                tenant_id="",
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _invoke(
        self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str, user: Optional[str] = None
    ) -> Iterator[bytes]:
        """
        Invoke TTS model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: voice to use
        :param user: unique user id
        :return: audio chunks
        """
        group_id = credentials.get("minimax_group_id")
        api_key = credentials.get("minimax_api_key")

        if not group_id or not api_key:
            raise InvokeAuthorizationError("Missing required credentials: group_id and api_key")

        url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={group_id}"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        body = json.dumps(
            {
                "model": model,
                "text": content_text,
                "stream": True,
                "voice_setting": {"voice_id": voice, "speed": 1.0, "vol": 1.0, "pitch": 0},
                "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
            }
        )

        try:
            response = requests.post(url, headers=headers, data=body, stream=True)
            response.raise_for_status()

            for chunk in response.raw:
                if chunk and chunk.startswith(b"data:"):
                    data = json.loads(chunk[5:])
                    if "data" in data and "extra_info" not in data and "audio" in data["data"]:
                        yield bytes.fromhex(data["data"]["audio"])

        except requests.exceptions.RequestException as e:
            raise self._transform_invoke_error(e, model)

    def get_model_schema(self, model: str, credentials: dict) -> dict:
        """
        Get model schema

        :param model: model name
        :param credentials: model credentials
        :return: model schema
        """
        return {
            "model_properties": {
                ModelPropertyKey.VOICES: [
                    {"name": "青涩青年音色", "value": "male-qn-qingse", "language": "zh-CN"},
                    {"name": "精英青年音色", "value": "male-qn-jingying", "language": "zh-CN"},
                    {"name": "霸道青年音色", "value": "male-qn-badao", "language": "zh-CN"},
                    {"name": "青年大学生音色", "value": "male-qn-daxuesheng", "language": "zh-CN"},
                    {"name": "少女音色", "value": "female-shaonv", "language": "zh-CN"},
                    {"name": "御姐音色", "value": "female-yujie", "language": "zh-CN"},
                    {"name": "成熟女性音色", "value": "female-chengshu", "language": "zh-CN"},
                    {"name": "甜美女性音色", "value": "female-tianmei", "language": "zh-CN"},
                    {"name": "男性主持人", "value": "presenter_male", "language": "zh-CN"},
                    {"name": "女性主持人", "value": "presenter_female", "language": "zh-CN"},
                    {"name": "男性有声书1", "value": "audiobook_male_1", "language": "zh-CN"},
                    {"name": "男性有声书2", "value": "audiobook_male_2", "language": "zh-CN"},
                    {"name": "女性有声书1", "value": "audiobook_female_1", "language": "zh-CN"},
                    {"name": "女性有声书2", "value": "audiobook_female_2", "language": "zh-CN"},
                    {"name": "青涩青年音色", "value": "beta：male-qn-qingse-jingpin", "language": "zh-CN"},
                    {"name": "精英青年音色", "value": "beta：male-qn-jingying-jingpin", "language": "zh-CN"},
                    {"name": "霸道青年音色", "value": "beta：male-qn-badao-jingpin", "language": "zh-CN"},
                    {"name": "青年大学生音色", "value": "beta：male-qn-daxuesheng-jingpin", "language": "zh-CN"},
                    {"name": "少女音色", "value": "beta：female-shaonv-jingpin", "language": "zh-CN"},
                    {"name": "御姐音色", "value": "beta：female-yujie-jingpin", "language": "zh-CN"},
                    {"name": "成熟女性音色", "value": "beta：female-chengshu-jingpin", "language": "zh-CN"},
                    {"name": "甜美女性音色", "value": "beta：female-tianmei-jingpin", "language": "zh-CN"},
                    {"name": "聪明男童", "value": "clever_boy", "language": "zh-CN"},
                    {"name": "可爱男童", "value": "cute_boy", "language": "zh-CN"},
                    {"name": "萌萌女童", "value": "lovely_girl", "language": "zh-CN"},
                    {"name": "卡通猪小琪", "value": "cartoon_pig", "language": "zh-CN"},
                    {"name": "病娇弟弟", "value": "bingjiao_didi", "language": "zh-CN"},
                    {"name": "俊朗男友", "value": "junlang_nanyou", "language": "zh-CN"},
                    {"name": "纯真学弟", "value": "chunzhen_xuedi", "language": "zh-CN"},
                    {"name": "冷淡学长", "value": "lengdan_xiongzhang", "language": "zh-CN"},
                    {"name": "霸道少爷", "value": "badao_shaoye", "language": "zh-CN"},
                    {"name": "甜心小玲", "value": "tianxin_xiaoling", "language": "zh-CN"},
                    {"name": "俏皮萌妹", "value": "qiaopi_mengmei", "language": "zh-CN"},
                    {"name": "妩媚御姐", "value": "wumei_yujie", "language": "zh-CN"},
                    {"name": "嗲嗲学妹", "value": "diadia_xuemei", "language": "zh-CN"},
                    {"name": "淡雅学姐", "value": "danya_xuejie", "language": "zh-CN"},
                    {"name": "Santa Claus", "value": "Santa_Claus", "language": "zh-CN"},
                    {"name": "Grinch", "value": "Grinch", "language": "zh-CN"},
                    {"name": "Rudolph", "value": "Rudolph", "language": "zh-CN"},
                    {"name": "Arnold", "value": "Arnold", "language": "zh-CN"},
                    {"name": "Charming Santa", "value": "Charming_Santa", "language": "zh-CN"},
                    {"name": "Charming Lady", "value": "Charming_Lady", "language": "zh-CN"},
                    {"name": "Sweet Girl", "value": "Sweet_Girl", "language": "zh-CN"},
                    {"name": "Cute Elf", "value": "Cute_Elf", "language": "zh-CN"},
                    {"name": "Attractive Girl", "value": "Attractive_Girl", "language": "zh-CN"},
                    {"name": "Serene Woman", "value": "Serene_Woman", "language": "zh-CN"},
                ],
                ModelPropertyKey.DEFAULT_VOICE: "male-qn-qingse",
                ModelPropertyKey.AUDIO_TYPE: "mp3",
                ModelPropertyKey.WORD_LIMIT: 8000,
                ModelPropertyKey.MAX_WORKERS: 5,
            }
        }

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeConnectionError: [requests.exceptions.ConnectionError],
            InvokeServerUnavailableError: [requests.exceptions.HTTPError, requests.exceptions.Timeout],
            InvokeRateLimitError: [requests.exceptions.TooManyRedirects],
            InvokeAuthorizationError: [requests.exceptions.HTTPError, ValueError],
            InvokeBadRequestError: [requests.exceptions.RequestException, KeyError, json.JSONDecodeError],
        }

    def _get_model_default_voice(self, model: str, credentials: dict) -> Any:
        schema = self.get_model_schema(model, credentials)
        return schema["model_properties"][ModelPropertyKey.DEFAULT_VOICE]

    def _get_model_word_limit(self, model: str, credentials: dict) -> int:
        schema = self.get_model_schema(model, credentials)
        return schema["model_properties"][ModelPropertyKey.WORD_LIMIT]

    def _get_model_audio_type(self, model: str, credentials: dict) -> str:
        schema = self.get_model_schema(model, credentials)
        return schema["model_properties"][ModelPropertyKey.AUDIO_TYPE]

    def _get_model_workers_limit(self, model: str, credentials: dict) -> int:
        schema = self.get_model_schema(model, credentials)
        return schema["model_properties"][ModelPropertyKey.MAX_WORKERS]

    def get_tts_model_voices(self, model: str, credentials: dict, language: Optional[str] = None) -> list:
        """
        Get available voices for the model
        """
        schema = self.get_model_schema(model, credentials)
        voices = schema["model_properties"][ModelPropertyKey.VOICES]

        if language:
            return [v for v in voices if v["language"] == language]
        return voices
