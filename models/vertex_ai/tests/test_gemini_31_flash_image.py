from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from dify_plugin.entities.model.message import UserPromptMessage
from google.genai import types

from models.llm import llm

MODEL = "gemini-3.1-flash-image"


def _rules(name: str) -> tuple[dict, dict]:
    path = Path(__file__).parents[1] / f"models/llm/{name}.yaml"
    schema = yaml.safe_load(path.read_text())
    return schema, {r["name"]: r for r in schema["parameter_rules"]}


def test_ga_schema():
    schema, rules = _rules(MODEL)
    assert schema["model"] == MODEL
    assert schema["model_properties"]["context_size"] == 131072
    assert rules["max_output_tokens"]["max"] == 32768
    assert rules["resolution"]["options"] == ["512", "1K", "2K", "4K"]
    assert {"1:4", "1:8"} <= set(rules["aspect_ratio"]["options"])
    # Documented but rejected by Vertex AI with 400 INVALID_ARGUMENT.
    assert "9:21" not in rules["aspect_ratio"]["options"]


def test_preview_is_kept():
    schema, _ = _rules("gemini-3.1-flash-image-preview")
    assert schema["model"] == "gemini-3.1-flash-image-preview"


def test_ga_is_image_model_on_global_endpoint():
    assert MODEL in llm.IMAGE_GENERATION_MODELS
    assert MODEL in llm.GLOBAL_ONLY_MODELS_DEFAULT


def test_every_listed_option_reaches_image_config():
    _, rules = _rules(MODEL)
    for ratio in rules["aspect_ratio"]["options"]:
        for resolution in rules["resolution"]["options"]:
            config = types.GenerateContentConfig()
            llm.VertexAiLargeLanguageModel._set_image_config(
                config=config,
                model_parameters={"aspect_ratio": ratio, "resolution": resolution},
                model=MODEL,
            )
            expected_ratio = None if ratio == "Auto" else ratio
            assert config.image_config.aspect_ratio == expected_ratio
            assert config.image_config.image_size == resolution


@pytest.mark.parametrize("stream", [False, True])
def test_ga_request_config(monkeypatch, stream):
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=Mock(return_value="response"),
            generate_content_stream=Mock(return_value=iter(())),
        )
    )
    create = Mock(return_value=client)
    monkeypatch.setattr(llm.genai, "Client", create)
    model = llm.VertexAiLargeLanguageModel([])
    monkeypatch.setattr(model, "_handle_generate_response", lambda *a: "handled")
    monkeypatch.setattr(
        model, "_handle_generate_stream_response", lambda *a: "stream handled"
    )
    model._generate(
        MODEL,
        {"vertex_project_id": "test-project", "vertex_location": "us-central1"},
        [UserPromptMessage(content="Draw a diagram")],
        {"aspect_ratio": "1:4", "resolution": "512", "max_output_tokens": 32768},
        stream=stream,
    )
    assert create.call_args.kwargs["location"] == "global"
    call = (
        client.models.generate_content_stream
        if stream
        else client.models.generate_content
    )
    config = call.call_args.kwargs["config"]
    assert config.response_modalities == ["TEXT", "IMAGE"]
    assert config.image_config.aspect_ratio == "1:4"
    assert config.image_config.image_size == "512"
