import json
import logging
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)

class MinimaxTTS(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            group_id = self.runtime.credentials["group_id"]
            api_key = self.runtime.credentials["api_key"]
        except KeyError:
            raise Exception("group_id 或 api_key 未配置或无效")

        text = tool_parameters.get("text", "")
        if not text:
            yield self.create_text_message("文本内容不能为空")

        # 兼容 voice_id 和 VoiceID
        voice_id = tool_parameters.get("voice_id") or tool_parameters.get("VoiceID") or "male-qn-qingse"
        model = tool_parameters.get("model", "speech-02-hd")
        language_boost = tool_parameters.get("language_boost", "auto")
        emotion = tool_parameters.get("emotion", "happy")  # 默认 happy
        vol = tool_parameters.get("vol", 1)  # 默认 1
        try:
            vol = float(vol)
            if not (0 < vol <= 10):
                vol = 1
        except Exception:
            vol = 1

        voice_setting = {
            "voice_id": voice_id,
            "vol": vol
        }
        if emotion:
            voice_setting["emotion"] = emotion

        url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={group_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "model": model,
            "language_boost": language_boost,
            "voice_setting": voice_setting,
            "audio_type": "mp3"
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=(10, 30))
            response.raise_for_status()
            parsed_json = response.json()
            audio_hex = parsed_json.get("data", {}).get("audio")
            if not audio_hex:
                yield self.create_text_message("API 未返回音频数据")
                return
            audio_bytes = bytes.fromhex(audio_hex)
            yield self.create_blob_message(audio_bytes, meta={"mime_type": "audio/mpeg"})
        except requests.exceptions.ReadTimeout:
            yield self.create_text_message("请求超时，请稍后重试")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message("网络连接错误，请检查网络设置")
        except requests.exceptions.RequestException as e:
            error_msg = "请求失败"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg = error_data["error"]
            except:
                pass
            yield self.create_text_message(f"{error_msg}: {str(e)}")

    def tts(self, text: str, group_id: str, api_key: str) -> bytes:
        """调用 MiniMax TTS API 进行文本转语音"""
        url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={group_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = json.dumps({
            "text": text,
            "model": "speech-01",
            "voice_id": "male-qn-qingse",
            "audio_type": "mp3"
        })

        try:
            response = requests.post(url, headers=headers, data=payload, timeout=(10, 30))
            response.raise_for_status()
            return response.content
        except requests.exceptions.ReadTimeout:
            raise Exception("请求超时，请稍后重试")
        except requests.exceptions.ConnectionError:
            raise Exception("网络连接错误，请检查网络设置")
        except requests.exceptions.RequestException as e:
            error_msg = "请求失败"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg = error_data["error"]
            except:
                pass
            raise Exception(f"{error_msg}: {str(e)}")

    def validate(self) -> None:
        """验证凭据"""
        try:
            group_id = self.runtime.credentials["group_id"]
            api_key = self.runtime.credentials["api_key"]
        except KeyError:
            raise Exception("group_id 或 api_key 未配置或无效")

        try:
            self.tts("test", group_id, api_key)
        except Exception as e:
            raise Exception(f"验证凭据失败: {str(e)}") 