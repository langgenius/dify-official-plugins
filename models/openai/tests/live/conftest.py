from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity

from models.llm.llm import OpenAILargeLanguageModel
from models.moderation.moderation import OpenAIModerationModel
from models.speech2text.speech2text import OpenAISpeech2TextModel
from models.text_embedding.text_embedding import OpenAITextEmbeddingModel
from models.tts.tts import OpenAIText2SpeechModel

ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = ROOT / "models"


class _Credentials(dict[str, str]):
    def __repr__(self) -> str:
        return f"OpenAI test credentials ({', '.join(sorted(self))})"

    __str__ = __repr__


def _model_names(model_type: str) -> list[str]:
    directory = MODEL_ROOT / model_type
    if model_type == "llm":
        return yaml.safe_load((directory / "_position.yaml").read_text())
    return sorted(
        path.stem for path in directory.glob("*.yaml") if not path.name.startswith("_")
    )


def _schemas(model_type: str) -> list[AIModelEntity]:
    directory = MODEL_ROOT / model_type
    return [
        AIModelEntity.model_validate(
            yaml.safe_load((directory / f"{model}.yaml").read_text())
        )
        for model in _model_names(model_type)
    ]


def _selected(request: pytest.FixtureRequest, model: str) -> str:
    selected = set(request.config.getoption("live_models"))
    if selected and model not in selected:
        pytest.skip("model not selected by --live-model")
    return model


@pytest.fixture(scope="session")
def live_credentials() -> _Credentials:
    credentials = _Credentials(openai_api_key=os.environ["OPENAI_API_KEY"])
    if organization := os.getenv("OPENAI_ORGANIZATION"):
        credentials["openai_organization"] = organization
    if base_url := os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE"):
        credentials["openai_api_base"] = base_url
    return credentials


@pytest.fixture(scope="session")
def live_llm() -> OpenAILargeLanguageModel:
    return OpenAILargeLanguageModel(_schemas("llm"))


@pytest.fixture(scope="session")
def live_embedding() -> OpenAITextEmbeddingModel:
    return OpenAITextEmbeddingModel(_schemas("text_embedding"))


@pytest.fixture(scope="session")
def live_moderation() -> OpenAIModerationModel:
    return OpenAIModerationModel(_schemas("moderation"))


@pytest.fixture(scope="session")
def live_speech2text() -> OpenAISpeech2TextModel:
    return OpenAISpeech2TextModel(_schemas("speech2text"))


@pytest.fixture(scope="session")
def live_tts() -> OpenAIText2SpeechModel:
    return OpenAIText2SpeechModel(_schemas("tts"))


@pytest.fixture(params=_model_names("llm"), ids=str)
def llm_model(request: pytest.FixtureRequest) -> str:
    return _selected(request, request.param)


@pytest.fixture(params=_model_names("text_embedding"), ids=str)
def embedding_model(request: pytest.FixtureRequest) -> str:
    return _selected(request, request.param)


@pytest.fixture(params=_model_names("moderation"), ids=str)
def moderation_model(request: pytest.FixtureRequest) -> str:
    return _selected(request, request.param)


@pytest.fixture(params=_model_names("speech2text"), ids=str)
def speech2text_model(request: pytest.FixtureRequest) -> str:
    return _selected(request, request.param)


@pytest.fixture(params=_model_names("tts"), ids=str)
def tts_model(request: pytest.FixtureRequest) -> str:
    return _selected(request, request.param)


@pytest.fixture
def require_live_model(request: pytest.FixtureRequest):
    return lambda model: _selected(request, model)
