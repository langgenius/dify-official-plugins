import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import TokenerLargeLanguageModel

SCHEMAS = [
    AIModelEntity.model_validate(yaml.safe_load(path.read_text()))
    for path in Path("models/llm").glob("*.yaml")
    if path.name != "_position.yaml"
]


def response() -> requests.Response:
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(
        {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    ).encode()
    return result


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: s.model)
@pytest.mark.parametrize("stream", [False, True])
def test_public_invoke_keeps_declared_parameters(schema, stream) -> None:
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    declared = {rule.name for rule in schema.parameter_rules}
    parameters = {
        key: value
        for key, value in {
            "seed": 42,
            "temperature": 1.0,
            "top_p": 0.9,
            "presence_penalty": 0.1,
            "frequency_penalty": -0.1,
            "reasoning_effort": "low",
        }.items()
        if key in declared
    }
    original = parameters.copy()
    result = response()
    with (
        patch("requests.post", return_value=result) as post,
        patch.object(
            result,
            "iter_lines",
            return_value=iter(
                [
                    'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],'
                    '"usage":{"prompt_tokens":1,"completion_tokens":1}}',
                    "data: [DONE]",
                ]
            ),
        ),
    ):
        chunks = list(
            model.invoke(
                schema.model,
                {"api_key": "test"},
                [UserPromptMessage(content="Hi")],
                parameters,
                stream=stream,
            )
        )
    kwargs = post.call_args.kwargs
    body = kwargs["json"] if "json" in kwargs else json.loads(kwargs["data"])
    assert {key: body.get(key) for key in parameters} == parameters
    assert body["stream"] is stream
    assert chunks[0].delta.message.content == "ok"
    assert parameters == original


@pytest.mark.parametrize(
    "model_id,parameters",
    [
        ("gpt-5.6-luna", {"reasoning_effort": "minimal"}),
        ("gpt-5.6-luna", {"seed": True}),
        ("gpt-5.6-luna", {"seed": float("nan")}),
        ("deepseek-v4-pro", {"temperature": True}),
        ("deepseek-v4-pro", {"temperature": float("nan")}),
        ("deepseek-v4-pro", {"top_p": float("inf")}),
        ("deepseek-v4-pro", {"presence_penalty": False}),
        ("deepseek-v4-pro", {"frequency_penalty": float("-inf")}),
    ],
)
def test_public_invoke_rejects_invalid_declared_values(model_id, parameters) -> None:
    schema = next(s for s in SCHEMAS if s.model == model_id)
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    with patch("requests.post") as post, pytest.raises(ValueError):
        list(model.invoke(schema.model, {"api_key": "test"}, [], parameters))
    post.assert_not_called()


@pytest.mark.parametrize("model_id", ["gpt-5.6-luna", "deepseek-v4-pro"])
def test_public_invoke_handles_dify_builtin_sampling(model_id) -> None:
    schema = next(s for s in SCHEMAS if s.model == model_id)
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    parameters = {"temperature": 0.2, "top_p": 0.3, "max_tokens": 1500}
    with patch("requests.post", return_value=response()) as post:
        chunks = list(
            model.invoke(
                model_id,
                {"api_key": "test"},
                [UserPromptMessage(content="Hi")],
                parameters,
                stream=False,
            )
        )
    kwargs = post.call_args.kwargs
    body = kwargs["json"] if "json" in kwargs else json.loads(kwargs["data"])
    assert chunks[0].delta.message.content == "ok"
    assert body["max_tokens"] == 1500
    if model_id == "gpt-5.6-luna":
        assert "temperature" not in body
        assert "top_p" not in body
    else:
        assert body["temperature"] == 0.2
        assert body["top_p"] == 0.3
    assert parameters == {"temperature": 0.2, "top_p": 0.3, "max_tokens": 1500}


@pytest.mark.parametrize(
    "schema,rule_name",
    [
        pytest.param(schema, rule.name, id=f"{schema.model}-{rule.name}")
        for schema in SCHEMAS
        for rule in schema.parameter_rules
        if rule.type.value == "string" and rule.options
    ],
)
@pytest.mark.parametrize("toggle_on", [True, False])
def test_public_invoke_string_option_toggle_default(schema, rule_name, toggle_on) -> None:
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    rule = next(
        rule
        for rule in model.get_parameter_rules(schema.model, {"api_key": "test"})
        if rule.name == rule_name
    )
    toggle_value = rule.default or ""
    parameters = {rule.name: toggle_value} if toggle_on else {}
    with patch("requests.post", return_value=response()) as post:
        chunks = list(
            model.invoke(
                schema.model,
                {"api_key": "test"},
                [UserPromptMessage(content="Hi")],
                parameters,
                stream=False,
            )
        )
    post.assert_called_once()
    kwargs = post.call_args.kwargs
    body = kwargs["json"] if "json" in kwargs else json.loads(kwargs["data"])
    assert chunks[0].delta.message.content == "ok"
    if toggle_on:
        if rule.name == "response_format":
            assert body[rule.name] == {"type": "text"}
        else:
            assert body[rule.name] == toggle_value
    else:
        assert rule.name not in body
