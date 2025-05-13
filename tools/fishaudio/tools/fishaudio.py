from typing import Generator, Optional, Annotated, AsyncGenerator, Literal
import httpx
import ormsgpack
from pydantic import AfterValidator, BaseModel, conint, confloat
from dify_plugin.errors.model import InvokeBadRequestError

class ServeReferenceAudio(BaseModel):
    audio: bytes
    text: str

class TTSRequest(BaseModel):
    text: str
    chunk_length: Annotated[int, conint(ge=100, le=300, strict=True)] = 200
    # Audio format
    format: Literal["wav", "pcm", "mp3"] = "mp3"
    mp3_bitrate: Literal[64, 128, 192] = 192
    # References audios for in-context learning
    references: list[ServeReferenceAudio] = []
    # Reference id
    # For example, if you want use https://fish.audio/m/7f92f8afb8ec43bf81429cc1c9199cb1/
    # Just pass 7f92f8afb8ec43bf81429cc1c9199cb1
    reference_id: str | None = None
    prosody: dict | None = None
    # Normalize text for en & zh, this increase stability for numbers
    normalize: bool = True
    # Balance mode will reduce latency to 300ms, but may decrease stability
    latency: Literal["normal", "balanced"] = "normal"

class FishAudio():
    def __init__(self, url_base, api_key, tts_model = None):
        self.url_base = url_base
        self.api_key = api_key
        self.tts_model = tts_model
        if not api_key:
            raise InvokeBadRequestError("API key not found")

    def headers(self):
        if not self.tts_model:
            return {
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/msgpack",
            }
        else:
            return {
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/msgpack",
                "model": self.tts_model,
            }

    def tts(self, content, voice, latency, audio_format, audio_speed: Annotated[float, confloat(ge=0.5, le=2.0, strict=True)] = 1, chunk_length: Annotated[int, conint(ge=100, le=300, strict=True)] = 200, normalize: bool = True) -> Generator[bytes, None, None]:
        request = TTSRequest(
            text=content,
            format=audio_format,
            reference_id=voice,
            prosody= {
                "speed": audio_speed
            },
            chunk_length=chunk_length,
            normalize=normalize,
            latency=latency,
        )
        try:
            with httpx.stream(
                    "POST",
                    self.url_base + "/v1/tts",
                    content=ormsgpack.packb(request, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
                    headers=self.headers(),
                    timeout=None,
            ) as response:
                response.raise_for_status()
                yield from response.iter_bytes()
        except httpx.HTTPStatusError as e:
            raise InvokeBadRequestError(f"{e.response.status_code} - {str(e)}")

    def model_list(self, page_number):
        params = {
            "page_size": 20,
            "page_number": 1,
            "sort_by": "score",
            "language": "zh",
            "title_language": "zh"
        }
        r = httpx.get(self.url_base + "/model",
                      headers=self.headers(),
                      params=params,)
        if r.status_code != 200:
            r.raise_for_status()
        return ""
