from typing import Generator, Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from fish_audio_sdk import Session, TTSRequest

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

        audio_format = tool_parameters.get("format", "wav")
        latency = tool_parameters.get("latency", "normal")
        model = tool_parameters.get("model", "speech-1.5")
        speed = tool_parameters.get("speed", 1.0)
        volume = tool_parameters.get("volume", 0)
        try:
            data = self._tts(content, voice_id, audio_format, latency, model, speed, volume)
            yield self.create_blob_message(blob=data, meta={"mime_type": f"audio/{audio_format}"})
        except Exception as e:
            yield self.create_text_message(f"Text to speech service error, please check the network; error: {e}")
        
    def _tts(self, content: str, voice_id: str, audio_format: str, latency: str, model: str, speed: float, volume: float) -> bytes:
        api_key = self.runtime.credentials.get("api_key")
        api_base = self.runtime.credentials.get("api_base")
        session = Session(api_key, base_url=api_base)
        request = TTSRequest(
            text=content,
            format=audio_format,
            reference_id=voice_id,
            latency=latency,
            prosody={
                "speed": speed,
                "volume": volume
            }
        )
        try:
            gen = session.tts(request, backend=model)
            res = b"".join(gen)
            return res
        except Exception as e:
            raise e
