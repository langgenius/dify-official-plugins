import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage

from models.llm.llm import TokenerLargeLanguageModel

_OMITTED = object()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "tool_choice",
    [
        pytest.param(_OMITTED, id="omitted"),
        pytest.param(None, id="null"),
        "none",
        "auto",
        "required",
        {"type": "function", "function": {"name": "lookup"}},
    ],
)
def test_public_invoke_preserves_tool_choice(stream, tool_choice) -> None:
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text())
    )
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    response = requests.Response()
    response.status_code = 200
    payload = {
        "id": "completion",
        "model": schema.model,
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    response._content = (
        'data: {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}], '
        '"usage": {"prompt_tokens": 1, "completion_tokens": 1}}\n\ndata: [DONE]\n\n'
        if stream
        else json.dumps(payload)
    ).encode()
    response._content_consumed = True
    parameters = {"max_tokens": 10}
    if tool_choice is not _OMITTED:
        parameters["tool_choice"] = tool_choice
    original_parameters = parameters.copy()
    credentials = {"api_key": "test-key"}
    with patch("requests.post", return_value=response) as post:
        chunks = list(
            model.invoke(
                model=schema.model,
                credentials=credentials,
                prompt_messages=[UserPromptMessage(content="Use lookup")],
                model_parameters=parameters,
                tools=[
                    PromptMessageTool(
                        name="lookup",
                        description="Lookup",
                        parameters={
                            "type": "object",
                            "properties": {"x": {"type": "integer"}},
                        },
                    )
                ],
                stream=stream,
                stop=["END"],
                user="user-1",
            )
        )
    kwargs = post.call_args.kwargs
    body = kwargs["json"] if "json" in kwargs else json.loads(kwargs["data"])
    assert body["tool_choice"] == (
        tool_choice if tool_choice is not _OMITTED and tool_choice is not None else "auto"
    )
    assert body["tools"][0]["function"]["name"] == "lookup"
    assert body["stream"] is stream
    assert body["max_tokens"] == 10
    assert body["stop"] == ["END"]
    assert body["user"] == "user-1"
    assert chunks[0].delta.message.content == "ok"
    assert parameters == original_parameters
    assert credentials == {"api_key": "test-key"}


@pytest.mark.parametrize("tool_choice", ["none", "required"])
def test_public_invoke_without_tools_omits_tool_choice(tool_choice) -> None:
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text())
    )
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    ).encode()
    with patch("requests.post", return_value=response) as post:
        list(
            model.invoke(
                model=schema.model,
                credentials={"api_key": "test-key"},
                prompt_messages=[UserPromptMessage(content="Hello")],
                model_parameters={"tool_choice": tool_choice},
                stream=False,
            )
        )
    kwargs = post.call_args.kwargs
    body = kwargs["json"] if "json" in kwargs else json.loads(kwargs["data"])
    assert "tool_choice" not in body
    assert "tools" not in body
