from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import UserPromptMessage

from models.common_telnyx import _CommonTelnyx
from models.llm.llm import TelnyxLargeLanguageModel
from models.speech2text.speech2text import TelnyxSpeech2TextModel
from models.text_embedding.text_embedding import TelnyxTextEmbeddingModel
from models.tts.tts import TelnyxText2SpeechModel


TELNYX_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_LLM_MODELS = [
    "moonshotai/Kimi-K2.6",
    "zai-org/GLM-5.1-FP8",
    "MiniMaxAI/MiniMax-M2.7",
    "Qwen/Qwen3-235B-A22B",
    "moonshotai/Kimi-K2.5",
    "openai/gpt-5.2",
    "openai/gpt-5.1",
    "openai/gpt-5",
    "openai/gpt-4.1",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4-5",
    "google/gemini-2.5-flash",
    "Groq/gpt-oss-120b",
    "meta-llama/Llama-3.3-70B-Instruct",
    "meta-llama/Meta-Llama-3.1-70B-Instruct",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "google/gemma-2b-it",
]
EXPECTED_EMBEDDING_MODELS = [
    "Qwen/Qwen3-Embedding-8B",
    "intfloat/multilingual-e5-large",
    "thenlper/gte-large",
]
EXPECTED_STT_MODELS = ["openai/whisper-large-v3-turbo", "deepgram/nova-3"]
EXPECTED_TTS_VOICES = {
    "Telnyx.NaturalHD.astra",
    "Telnyx.NaturalHD.albion",
    "Telnyx.NaturalHD.luna",
    "Telnyx.NaturalHD.amarante",
    "Telnyx.KokoroTTS.af_alloy",
    "Telnyx.KokoroTTS.af_heart",
    "Telnyx.KokoroTTS.am_adam",
    "Telnyx.KokoroTTS.bf_emma",
    "Telnyx.KokoroTTS.ef_dora",
    "Telnyx.KokoroTTS.ff_siwis",
    "Telnyx.KokoroTTS.if_sara",
    "Telnyx.KokoroTTS.pf_dora",
}


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def model_dir(model_type: str) -> Path:
    return TELNYX_ROOT / "models" / model_type


def position(model_type: str) -> list[str]:
    return load_yaml(model_dir(model_type) / "_position.yaml")


def model_yamls(model_type: str) -> dict[str, dict]:
    models = {}
    for path in model_dir(model_type).glob("*.yaml"):
        if path.name == "_position.yaml":
            continue
        data = load_yaml(path)
        models[data["model"]] = data
    return models


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", lines=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else str(content)
        self.encoding = "utf-8"
        self._lines = lines or []

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1024):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line if decode_unicode else line.encode()


def credentials(**overrides):
    data = {"telnyx_api_key": "test-key"}
    data.update(overrides)
    return data


def test_predefined_model_positions_match_telnyx_model_lists():
    llm_models = model_yamls("llm")
    assert position("llm") == EXPECTED_LLM_MODELS
    assert set(llm_models) == set(EXPECTED_LLM_MODELS)
    assert llm_models["moonshotai/Kimi-K2.6"]["model_properties"]["context_size"] == 262144
    assert llm_models["openai/gpt-5.2"]["model_properties"]["context_size"] == 400000
    assert llm_models["google/gemma-2b-it"]["model_properties"]["context_size"] == 8192
    assert all(model.get("features") == ["tool-call"] for model in llm_models.values())

    embedding_models = model_yamls("text_embedding")
    assert position("text_embedding") == EXPECTED_EMBEDDING_MODELS
    assert set(embedding_models) == set(EXPECTED_EMBEDDING_MODELS)
    assert "dimension" not in embedding_models["Qwen/Qwen3-Embedding-8B"]["model_properties"]

    stt_models = model_yamls("speech2text")
    assert position("speech2text") == EXPECTED_STT_MODELS
    assert set(stt_models) == set(EXPECTED_STT_MODELS)
    assert stt_models["openai/whisper-large-v3-turbo"]["model_properties"]["file_upload_limit"] == 100
    assert stt_models["deepgram/nova-3"]["model_properties"]["supported_file_extensions"] == "mp3,wav"
    assert "oga" in stt_models["openai/whisper-large-v3-turbo"]["model_properties"]["supported_file_extensions"].split(",")


def test_yaml_model_entities_validate():
    for model_type in ("llm", "text_embedding", "speech2text", "tts"):
        for data in model_yamls(model_type).values():
            AIModelEntity.model_validate(data)


def test_tts_voice_list_covers_telnyx_documented_sample_voices():
    voices = {
        voice["mode"]
        for voice in model_yamls("tts")["telnyx-tts"]["model_properties"]["voices"]
    }
    assert EXPECTED_TTS_VOICES <= voices


def test_common_builds_telnyx_urls_without_v1_suffix():
    common = _CommonTelnyx()
    assert common._build_url(credentials(), "/v2/ai/chat/completions") == "https://api.telnyx.com/v2/ai/chat/completions"
    assert common._build_url(credentials(telnyx_api_base="https://proxy.example/base/"), "/v2/x") == "https://proxy.example/base/v2/x"


@patch("models.common_telnyx.requests.post")
def test_embeddings_url_auth_header_and_float_vector_parsing(mock_post):
    mock_post.return_value = FakeResponse(
        payload={
            "model": "thenlper/gte-large",
            "data": [{"index": 0, "embedding": [1, "2.5", 3.0]}],
            "usage": {"total_tokens": 4},
        }
    )
    model = TelnyxTextEmbeddingModel(model_schemas=[])

    result = model._invoke("thenlper/gte-large", credentials(), ["hello"])

    assert result.embeddings == [[1.0, 2.5, 3.0]]
    call = mock_post.call_args
    assert call.args[0] == "https://api.telnyx.com/v2/ai/openai/embeddings"
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call.kwargs["json"]["input"] == ["hello"]


@patch("models.tts.tts.requests.post")
def test_tts_posts_text_voice_and_returns_audio_chunks(mock_post):
    mock_post.return_value = FakeResponse(content=b"abcdef")
    model = TelnyxText2SpeechModel(model_schemas=[])
    with patch.object(model, "_get_model_audio_type", return_value="mp3"):
        chunks = list(model._tts_invoke_streaming("telnyx-tts", credentials(), "hello", "Telnyx.NaturalHD.astra"))

    assert b"".join(chunks) == b"abcdef"
    call = mock_post.call_args
    assert call.args[0] == "https://api.telnyx.com/v2/text-to-speech/speech"
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call.kwargs["json"] == {
        "text": "hello",
        "voice": "Telnyx.NaturalHD.astra",
        "output_format": "mp3",
        "model": "telnyx-tts",
    }


@patch("models.speech2text.speech2text.requests.post")
def test_speech2text_multipart_extracts_text(mock_post):
    mock_post.return_value = FakeResponse(payload={"text": "hello world"})
    model = TelnyxSpeech2TextModel(model_schemas=[])
    audio = BytesIO(b"audio")
    audio.name = "sample.wav"

    text = model._invoke("openai/whisper-large-v3-turbo", credentials(), audio)

    assert text == "hello world"
    call = mock_post.call_args
    assert call.args[0] == "https://api.telnyx.com/v2/ai/audio/transcriptions"
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert "Content-Type" not in call.kwargs["headers"]
    assert call.kwargs["data"]["model"] == "openai/whisper-large-v3-turbo"
    assert call.kwargs["files"]["file"][0] == "sample.wav"


@patch("models.common_telnyx.requests.post")
def test_llm_non_streaming_payload_and_parsing(mock_post):
    mock_post.return_value = FakeResponse(
        payload={
            "model": "Qwen/Qwen3-235B-A22B",
            "choices": [{"message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    )
    model = TelnyxLargeLanguageModel(model_schemas=[])
    fake_usage = LLMUsage(
        prompt_tokens=3,
        prompt_unit_price=0,
        prompt_price_unit=0,
        prompt_price=0,
        completion_tokens=2,
        completion_unit_price=0,
        completion_price_unit=0,
        completion_price=0,
        total_tokens=5,
        total_price=0,
        currency="USD",
        latency=0,
    )
    with patch.object(model, "_calc_response_usage", return_value=fake_usage):
        result = model._invoke(
            model="Qwen/Qwen3-235B-A22B",
            credentials=credentials(),
            prompt_messages=[UserPromptMessage(content="ping")],
            model_parameters={"temperature": 0.1, "max_tokens": 8},
            stream=False,
        )

    assert result.message.content == "pong"
    call = mock_post.call_args
    assert call.args[0] == "https://api.telnyx.com/v2/ai/chat/completions"
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call.kwargs["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert call.kwargs["json"]["stream"] is False
    assert call.kwargs["json"]["temperature"] == 0.1
