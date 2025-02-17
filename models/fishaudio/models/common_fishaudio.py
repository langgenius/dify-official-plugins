from ast import Str
from typing import Generator, Optional, Annotated, AsyncGenerator, Literal
import httpx
import ormsgpack
from pydantic import AfterValidator, BaseModel, conint
from dify_plugin.errors.model import InvokeBadRequestError
import requests

class ServeReferenceAudio(BaseModel):
    audio: bytes
    text: str

class TTSRequest(BaseModel):
    text: str
    chunk_length: Annotated[int, conint(ge=100, le=300, strict=True)] = 200
    # Audio format
    format: Literal["wav", "pcm", "mp3"] = "mp3"
    mp3_bitrate: Literal[64, 128, 192] = 128
    # References audios for in-context learning
    references: list[ServeReferenceAudio] = []
    # Reference id
    # For example, if you want use https://fish.audio/m/7f92f8afb8ec43bf81429cc1c9199cb1/
    # Just pass 7f92f8afb8ec43bf81429cc1c9199cb1
    reference_id: str | None = None
    # Normalize text for en & zh, this increase stability for numbers
    normalize: bool = True
    # Balance mode will reduce latency to 300ms, but may decrease stability
    latency: Literal["normal", "balanced"] = "normal"

class FishAudio():
    def __init__(self, url_base, api_key):
        self.url_base = url_base
        self.api_key = api_key
        if not api_key:
            raise InvokeBadRequestError("API key not found")

    def headers(self):
        return {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/msgpack",
        }

    def tts(self, content, voice, latency, format="mp3") -> Generator[bytes, None, None]:
        request = TTSRequest(
            text=content,
        )
        
        with httpx.Client() as client:
            response = client.post(
                self.url_base + "/v1/tts",
                headers=self.headers(),
                json={
                    "text":content,
                    "reference_id": voice,
                    "latency": latency,
                    "format": format,
                },
                timeout=None,
                content=ormsgpack.packb(request, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
            )
            if response.status_code != 200:
                raise InvokeBadRequestError(f"Error: {response.status_code} - {response.text}")
            for chunk in response.iter_bytes():
                yield chunk
        

    def asr(self, audio_data) -> str:
        request_data = {
            "audio": audio_data,
            "ignore_timestamps": False
        }

        with httpx.Client() as client:
            response = client.post(
                self.url_base + "/v1/asr",
                headers=self.headers(),
                content=ormsgpack.packb(request_data),
            )
        result = response.json()
        if response.status_code != 200:
            raise InvokeBadRequestError(f"Error: {response.status_code} - {response.text}")
        return result["text"]
        
