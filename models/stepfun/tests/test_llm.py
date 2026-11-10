import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import UserPromptMessage
from models.llm.llm import StepfunLargeLanguageModel


@pytest.fixture
def llm():
    instance = StepfunLargeLanguageModel([])
    instance._calc_response_usage = Mock(return_value=None)
    return instance


def stream(llm, events):
    response = Mock()
    response.iter_lines.return_value = [
        ": keepalive",
        "",
        *["data: " + (e if isinstance(e, str) else json.dumps(e)) for e in events],
    ]
    return list(
        llm._handle_generate_stream_response(
            "step-5-preview", {}, response, [UserPromptMessage(content="hello")]
        )
    )


def event(delta, finish=None):
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


def test_parallel_same_name_calls_and_usage(llm):
    chunks = stream(
        llm,
        [
            event({"reasoning_content": "plan"}),
            event({"reasoning_content": ""}),
            event(
                {
                    "tool_calls": [
                        {
                            "index": i,
                            "id": f"call_{i}",
                            "type": "function",
                            "function": {"name": "search", "arguments": '{"q":"'},
                        }
                        for i in range(2)
                    ]
                }
            ),
            event(
                {
                    "tool_calls": [
                        {"index": 1, "function": {"arguments": 'b"}'}},
                        {"index": 0, "function": {"arguments": 'a"}'}},
                    ]
                },
                "tool_calls",
            ),
            {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            "[DONE]",
        ],
    )
    assert "".join(c.delta.message.content or "" for c in chunks) == "<think>plan</think>"
    calls = [t for c in chunks for t in c.delta.message.tool_calls]
    assert [t.id for t in calls] == ["call_0", "call_1"]
    assert [t.function.arguments for t in calls] == ['{"q":"a"}', '{"q":"b"}']
    assert chunks[-1].delta.finish_reason == "tool_calls"
    assert sum(c.delta.finish_reason is not None for c in chunks) == 1
    llm._calc_response_usage.assert_called_once_with("step-5-preview", {}, 100, 20)


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_reasoning_and_answer_in_same_chunk(llm, field):
    chunks = stream(
        llm,
        [
            event({field: "plan", "content": "answer"}, "stop"),
            {"choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0}},
            "[DONE]",
        ],
    )
    assert chunks[0].delta.message.content == "<think>plan</think>answer"
    llm._calc_response_usage.assert_called_once_with("step-5-preview", {}, 0, 0)


def test_reasoning_only_closes_and_missing_usage_estimates(llm):
    llm.get_num_tokens = Mock(return_value=12)
    llm._num_tokens_from_string = Mock(return_value=3)
    chunks = stream(llm, [event({"reasoning_content": "plan"}, "length"), "[DONE]"])
    assert "".join(c.delta.message.content or "" for c in chunks) == "<think>plan</think>"
    assert chunks[-1].delta.finish_reason == "length"
    llm.get_num_tokens.assert_called_once()
    llm._calc_response_usage.assert_called_once_with("step-5-preview", {}, 12, 3)


def test_upstream_stream_error(llm):
    with pytest.raises(ValueError, match="quota"):
        stream(llm, [{"error": {"message": "quota"}}])


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_non_streaming_reasoning(llm, field):
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": "answer", field: "plan"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }
    # Use the real SDK parser and real usage calculator.
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    result = llm._handle_generate_response("step-5-preview", {"mode": "chat"}, response, [])
    assert result.message.content == "<think>plan</think>answer"
    assert result.message.opaque_body == {"reasoning_content": "plan"}


@pytest.mark.parametrize("model", ["step-5-preview", "step-3.7-flash", "custom-model"])
def test_request_parameters(llm, model):
    llm._add_function_call = Mock()
    parameters = {"reasoning_effort": "high"}
    with patch.object(OAICompatLargeLanguageModel, "_invoke") as invoke:
        llm._invoke(model, {}, [], parameters)
    sent = invoke.call_args.args[3]
    assert sent.get("reasoning_format") == (None if model == "custom-model" else "deepseek-style")
    assert parameters == {"reasoning_effort": "high"}


def test_model_schema():
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "models/llm/step-5-preview.yaml").read_text())
    schema = AIModelEntity.model_validate(data)
    assert schema.model == "step-5-preview"
    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 1000000
    assert {"vision", "video", "tool-call"} <= set(data["features"])


def test_invoke_serializes_step5_request(llm):
    from dify_plugin.entities.model.message import (
        ImagePromptMessageContent,
        PromptMessageTool,
        TextPromptMessageContent,
    )

    schema = AIModelEntity.model_validate(
        yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "models/llm/step-5-preview.yaml").read_text()
        )
    )
    llm.get_model_schema = Mock(return_value=schema)
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    response = Mock(status_code=200, encoding="utf-8")
    response.json.return_value = {
        "choices": [{"message": {"content": '{"ok":true}', "reasoning_content": "plan"}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10},
    }
    with patch("requests.post", return_value=response) as post:
        result = llm._invoke(
            "step-5-preview",
            {"api_key": "test", "use_international_endpoint": "true"},
            [
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="describe"),
                        ImagePromptMessageContent(
                            data="https://example.com/test.png", format="png", mime_type="image/png"
                        ),
                    ]
                )
            ],
            {"max_tokens": 4096, "reasoning_effort": "high", "response_format": "json_object"},
            tools=[
                PromptMessageTool(
                    name="search", description="Search", parameters={"type": "object"}
                )
            ],
            stream=False,
        )
    assert post.call_args.args[0] == "https://api.stepfun.ai/v1/chat/completions"
    payload = json.loads(post.call_args.kwargs["data"])
    assert payload["reasoning_format"] == "deepseek-style"
    assert payload["reasoning_effort"] == "high"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["content"][1]["type"] == "image_url"
    assert payload["tools"][0]["function"]["name"] == "search"
    assert result.message.content == '<think>plan</think>{"ok":true}'
