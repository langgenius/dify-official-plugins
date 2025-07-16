import io
import json
from typing import Generator, Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from fish_audio_sdk import Session
import datetime

class CreateModel(Tool):
        def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
            """
            Create model by Fish Audio
            """
            api_key = self.runtime.credentials.get("api_key")
            api_base = self.runtime.credentials.get("api_base")
            session = Session(api_key, base_url=api_base)
            param = {
                "title": tool_parameters.get("title", ""),
            }
            voices = tool_parameters.get("audio")
            if isinstance(voices, list):
                voice_files = []
                for voice in voices:
                    if not isinstance(voice, File):
                        yield self.create_text_message("Error: All input audio must be valid files.")
                        return
                    try:
                        voice_bytes = voice.blob
                        voice_files.append(voice_bytes)
                    except Exception as e:
                        yield self.create_text_message(f"Error processing input audio: {e}")
                        # Clean up any opened files
                        return
                param["voices"] = voice_files
            else:
                if not isinstance(voices, File):
                    yield self.create_text_message("Error: Input audio must be a valid file.")
                    return
                try:
                    param["voices"] = voices.blob
                except Exception as e:
                    yield self.create_text_message(f"Error processing input audio: {e}")
                    return
            if tool_parameters.get("description"):
                param["description"] = tool_parameters.get("description")
            if tool_parameters.get("visibility"):
                param["visibility"] = tool_parameters.get("visibility")

            try:
                result = session.create_model(**param)
                yield self.create_text_message(f"Voice model created successfully. Model ID: {result.id}")
                yield self.create_json_message(result.model_dump())

            except Exception as e:
                yield self.create_text_message(f"Create model failed:{e}")

