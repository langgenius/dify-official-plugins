from typing import Generator, Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from .fishaudio import FishAudio

class Fishaudio(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tool
        
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
        voice_id = tool_parameters.get("voice_id", "")
        if not voice_id:
            yield self.create_text_message("Invalid parameter voice id")

        tts_model = tool_parameters.get("model")
        if tts_model and tts_model not in ["speech-1.5", "speech-1.6", "agent-x0"]:
            yield self.create_text_message("Invalid parameter tts model")

        audio_format = tool_parameters.get("format", "wav")
        audio_speed = tool_parameters.get("speed", 1.0)
        try:
            data = self._tts(content, voice_id, audio_format, tts_model, audio_speed)
            yield self.create_blob_message(blob=data, meta={"mime_type": f"audio/{audio_format}"})
        except Exception as e:
            yield self.create_text_message(f"Text to speech service error, please check the network; error: {e}")
        
    def _tts(self, content: str, voice_id: str, audio_format: str, tts_model: str = None, audio_speed: float = 1.0) -> bytes:
        api_key = self.runtime.credentials.get("api_key")
        api_base = self.runtime.credentials.get("api_base")
        balance_mode = self.runtime.credentials.get("latency")
        client = FishAudio(api_key=api_key, url_base=api_base, tts_model=tts_model)
        try:
            gen = client.tts(content, voice_id, balance_mode, audio_format, audio_speed)
            res = b"".join(gen)
            return res
        except Exception as e:
            raise e
