import concurrent.futures
import io
import random
import warnings
from typing import Any, Literal, Optional, Union, Generator
import openai
from yarl import URL
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from pydub import AudioSegment


class ToolParameterValidationError(Exception):
    pass


class PodcastAudioGeneratorTool(Tool):
    @staticmethod
    def _get_mime_type(output_format: str) -> str:
        mime_types = {
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
        }
        return mime_types.get(output_format, "audio/wav")

    @staticmethod
    def _generate_silence(duration: float):
        silence = AudioSegment.silent(duration=int(duration * 1000))
        return silence

    @staticmethod
    def _generate_audio_segment(
            client: openai.OpenAI,
            model: str,
            line: str,
            voice: Literal["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"],
            instructions: str,
            index: int,
    ) -> tuple[int, Union[AudioSegment, str], Optional[AudioSegment]]:
        try:
            response = client.audio.speech.create(
                model=model,
                voice=voice,
                instructions=instructions,
                input=line.strip(),
                response_format="wav"
            )
            audio = AudioSegment.from_wav(io.BytesIO(response.content))
            silence_duration = random.uniform(0.1, 1.5)
            silence = PodcastAudioGeneratorTool._generate_silence(silence_duration)
            return (index, audio, silence)
        except Exception as e:
            return (index, f"Error generating audio: {str(e)}", None)

    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        script = tool_parameters.get("script", "")
        host1_voice = tool_parameters.get("host1_voice")
        host2_voice = tool_parameters.get("host2_voice")
        host1_instructions = tool_parameters.get("host1_instructions", "")
        host2_instructions = tool_parameters.get("host2_instructions", "")
        channel_mode = tool_parameters.get("channel_mode", "mono")
        output_format = tool_parameters.get("output_format", "wav")
        script_lines = [line for line in script.split("\n") if line.strip()]
        if not host1_voice or not host2_voice:
            raise ToolParameterValidationError("Host voices are required")
        if not self.runtime or not self.runtime.credentials:
            raise ToolProviderCredentialValidationError("Tool runtime or credentials are missing")

        # initialize client based on TTS service
        tts_service = self.runtime.credentials.get("tts_service")
        if not tts_service:
            raise ToolProviderCredentialValidationError("TTS service is not specified")
        api_key = self.runtime.credentials.get("api_key")
        openai_base_url = self.runtime.credentials.get("openai_base_url", None)
        model = self.runtime.credentials.get("model", None)
        if tts_service == "openai":
            if not api_key:
                raise ToolProviderCredentialValidationError("OpenAI API key is missing")
            openai_base_url = str(URL(openai_base_url) / "v1") if openai_base_url else None
            if not model:
                model = "tts-1"
            client = openai.OpenAI(api_key=api_key, base_url=openai_base_url)
        elif tts_service == "azure_openai":
            if not api_key:
                raise ToolProviderCredentialValidationError("Azure OpenAI API key is missing")
            if not openai_base_url:
                raise ToolProviderCredentialValidationError("API Base URL is required for Azure OpenAI")
            if not model:
                raise ToolProviderCredentialValidationError("Model is required for Azure OpenAI")
            client = openai.AzureOpenAI(api_key=api_key, api_version="2025-04-01-preview", azure_endpoint=openai_base_url)

        # generate audio segments for each line in the script
        max_workers = 5
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, line in enumerate(script_lines):
                voice = host1_voice if i % 2 == 0 else host2_voice
                instructions = host1_instructions if i % 2 == 0 else host2_instructions
                future = executor.submit(self._generate_audio_segment, client, model, line, voice, instructions, i)
                futures.append(future)
            audio_segments: list[Any] = [None] * len(script_lines)
            for future in concurrent.futures.as_completed(futures):
                (index, audio, silence) = future.result()
                if isinstance(audio, str):
                    yield self.create_text_message(audio)
                audio_segments[index] = (audio, silence)

        # combine audio segments into a single audio file
        combined_audio = AudioSegment.empty()
        if channel_mode == "stereo":
            for i, (audio, silence) in enumerate(audio_segments):
                if audio:
                    pan_value = -0.2 if i % 2 == 0 else 0.2
                    stereo_audio = audio.set_channels(2).pan(pan_value)
                    combined_audio += stereo_audio
                    if i < len(audio_segments) - 1 and silence:
                        combined_audio += silence.set_channels(2)
        else:
            for i, (audio, silence) in enumerate(audio_segments):
                if audio:
                    combined_audio += audio
                    if i < len(audio_segments) - 1 and silence:
                        combined_audio += silence

        # export combined audio to bytes
        buffer = io.BytesIO()
        combined_audio.export(buffer, format=output_format)
        blob_bytes = buffer.getvalue()
        for resp in [
            self.create_text_message("Audio generated successfully"),
            self.create_blob_message(blob=blob_bytes, meta={"mime_type": self._get_mime_type(output_format)}),
        ]:
            yield resp
