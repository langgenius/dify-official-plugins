import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage

from models.llm.llm import TokenerLargeLanguageModel, model_family


def response(*, responses=False) -> requests.Response:
    result = requests.Response()
    result.status_code = 200
    result._content_consumed = True
    if responses:
        result._content = json.dumps(
            {
                "status": "completed",
                "output_text": "ok",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        ).encode()
        return result
    result._content = json.dumps(
        {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    ).encode()
    return result


@pytest.mark.parametrize("model_id", ["gpt-5.6-luna", "deepseek-v4-pro"])
def test_public_invoke_handles_dify_builtin_sampling(model_id) -> None:
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path(f"models/llm/{model_id}.yaml").read_text())
    )
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    parameters = {"temperature": 0.2, "top_p": 0.3, "max_tokens": 1500}
    if model_family(model_id) == "tongyi":
        parameters["enable_thinking"] = False
    with patch(
        "requests.post", return_value=response(responses=model_family(model_id) == "openai")
    ) as post:
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
    if model_family(model_id) == "openai":
        assert body["max_output_tokens"] == 1500
        assert body["temperature"] == 0.2
        assert body["top_p"] == 0.3
    else:
        assert body["max_tokens"] == 1500
        assert body["temperature"] == 0.2
        assert body["top_p"] == 0.3


def test_generic_catalog_model_keeps_tool_calls_on_the_fixed_endpoint():
    from models._credentials import ENDPOINT_URL

    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path("models/llm/kimi-k3.yaml").read_text())
    )
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    reply = response()
    reply._content = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": '{"id":1}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    ).encode()
    with patch("requests.post", return_value=reply) as post:
        result = model.invoke(
            schema.model,
            {"api_key": "test", "endpoint_url": "https://ignored.invalid"},
            [UserPromptMessage(content="Find record 1")],
            {},
            tools=[
                PromptMessageTool(
                    name="lookup", description="Find a record", parameters={"type": "object"}
                )
            ],
            stream=False,
        )
        message = list(result)[-1].delta.message
    assert post.call_args.args[0] == f"{ENDPOINT_URL}/chat/completions"
    assert message.tool_calls[0].function.name == "lookup"
    assert json.loads(message.tool_calls[0].function.arguments) == {"id": 1}
