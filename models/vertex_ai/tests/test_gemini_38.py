from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from dify_plugin.entities.model.message import UserPromptMessage
from google.genai import types

from models.llm import llm

MODEL = "gemini-3.8-flash"


def test_gemini_38_schema():
    path = Path(__file__).parents[1] / "models/llm/gemini-3.8-flash.yaml"
    schema = yaml.safe_load(path.read_text())
    assert schema["model"] == MODEL
    assert schema["model_properties"]["context_size"] == 1048576
    rules = {r["name"]: r for r in schema["parameter_rules"]}
    assert rules["max_output_tokens"]["max"] == 65536
    assert rules["thinking_level"]["options"] == ["Low", "Medium", "High"]
    assert (
        not {
            "temperature",
            "top_p",
            "top_k",
            "frequency_penalty",
            "presence_penalty",
            "candidate_count",
            "thinking_budget",
        }
        & rules.keys()
    )


@pytest.mark.parametrize("stream", [False, True])
def test_gemini_38_request_config(monkeypatch, stream):
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
    params = {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 4,
        "frequency_penalty": 1,
        "presence_penalty": 1,
        "candidate_count": 2,
        "thinking_budget": 100,
        "thinking_level": "Medium",
        "max_output_tokens": 65536,
    }
    model._generate(
        MODEL,
        {"vertex_project_id": "test-project", "vertex_location": "europe-west4"},
        [UserPromptMessage(content="Hi")],
        params,
        stream=stream,
    )
    assert create.call_args.kwargs["location"] == "global"
    call = (
        client.models.generate_content_stream
        if stream
        else client.models.generate_content
    )
    config = call.call_args.kwargs["config"]
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM
    assert config.thinking_config.thinking_budget is None
    for key in [
        "temperature",
        "top_p",
        "top_k",
        "frequency_penalty",
        "presence_penalty",
        "candidate_count",
    ]:
        assert getattr(config, key) is None
    assert params["temperature"] == 0.7


def test_existing_gemini_sampling_settings_unchanged(monkeypatch):
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=Mock(return_value="response"))
    )
    monkeypatch.setattr(llm.genai, "Client", Mock(return_value=client))
    model = llm.VertexAiLargeLanguageModel([])
    monkeypatch.setattr(model, "_handle_generate_response", lambda *a: "handled")
    model._generate(
        "gemini-3.7-flash",
        {"vertex_project_id": "test-project", "vertex_location": "us-central1"},
        [UserPromptMessage(content="Hi")],
        {"temperature": 0.7, "top_p": 0.8},
        stream=False,
    )
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.temperature == 0.7
    assert config.top_p == 0.8
