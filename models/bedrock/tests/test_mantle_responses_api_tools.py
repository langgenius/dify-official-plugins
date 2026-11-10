"""Tool calling on the bedrock-mantle / OpenAI Responses API path (GPT-5.x, GPT-6).

openai.yaml advertises tool-call / stream-tool-call, so Dify agents pass tools
for these models. The mantle path must forward them, replay tool calls and
tool results in the input, and return function_call items as tool calls.
No network: the openai client is mocked, stream events are stand-ins.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.llm import LLMUsage

llm_mod = importlib.import_module("models.llm.llm")

BedrockLLM = llm_mod.BedrockLargeLanguageModel
AssistantPromptMessage = llm_mod.AssistantPromptMessage
PromptMessageTool = llm_mod.PromptMessageTool
ToolPromptMessage = llm_mod.ToolPromptMessage
UserPromptMessage = llm_mod.UserPromptMessage

TOOL = PromptMessageTool(
    name="get_weather",
    description="Get current weather for one city",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)
CALL_ITEM = SimpleNamespace(
    type="function_call", call_id="call_1", name="get_weather", arguments='{"city":"Paris"}'
)


# The stream handler dispatches on type(event).__name__.
class ResponseOutputItemDoneEvent:
    def __init__(self, item) -> None:
        self.item = item


class ResponseCompletedEvent:
    def __init__(self, response=None) -> None:
        self.response = response


def _instance() -> BedrockLLM:
    instance = object.__new__(BedrockLLM)
    instance._calc_response_usage = MagicMock(
        return_value=LLMUsage.empty_usage()
    )
    return instance


def test_invoke_forwards_tools_to_mantle_path() -> None:
    instance = _instance()
    instance._generate_with_responses_api = MagicMock(return_value="RESULT")
    messages = [UserPromptMessage(content="Weather in Paris?")]
    instance._invoke("openai", {}, messages, {"model_name": "GPT-5.5"}, tools=[TOOL], stream=False)
    assert instance._generate_with_responses_api.call_args.args[-1] == [TOOL]


def test_tools_are_sent_as_function_tools() -> None:
    instance = _instance()
    instance._get_mantle_auth_token = MagicMock(return_value="token")
    instance._handle_responses_api_response = MagicMock(return_value="RESULT")
    client = MagicMock()
    with patch("openai.OpenAI", return_value=client):
        instance._generate_with_responses_api(
            "openai.gpt-5.5", {}, [UserPromptMessage(content="hi")], {}, stream=False, tools=[TOOL]
        )
        instance._generate_with_responses_api(
            "openai.gpt-5.5", {}, [UserPromptMessage(content="hi")], {}, stream=False
        )
    with_tools, without_tools = (c.kwargs for c in client.responses.create.call_args_list)
    assert with_tools["tools"] == [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get current weather for one city",
            "parameters": TOOL.parameters,
            "strict": False,
        }
    ]
    assert "tools" not in without_tools


def test_tool_calls_and_results_are_replayed_in_input() -> None:
    call = AssistantPromptMessage.ToolCall(
        id="call_1",
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name="get_weather", arguments='{"city":"Paris"}'
        ),
    )
    result = BedrockLLM._build_responses_api_input(
        _instance(),
        [
            UserPromptMessage(content="Weather in Paris?"),
            AssistantPromptMessage(content="", tool_calls=[call]),
            ToolPromptMessage(content="18C cloudy", tool_call_id="call_1", name="get_weather"),
        ],
    )
    assert result == [
        {"role": "user", "content": "Weather in Paris?"},
        {"type": "function_call", "call_id": "call_1", "name": "get_weather", "arguments": '{"city":"Paris"}'},
        {"type": "function_call_output", "call_id": "call_1", "output": "18C cloudy"},
    ]


def test_non_stream_function_call_becomes_tool_call() -> None:
    response = SimpleNamespace(
        output_text="",
        output=[SimpleNamespace(type="reasoning"), CALL_ITEM],
        usage=SimpleNamespace(input_tokens=3, output_tokens=5),
    )
    result = _instance()._handle_responses_api_response("openai.gpt-5.5", {}, response, [])
    [tool_call] = result.message.tool_calls
    assert (tool_call.id, tool_call.function.name, tool_call.function.arguments) == (
        "call_1", "get_weather", '{"city":"Paris"}'
    )


def test_stream_function_call_item_yields_tool_call_chunk() -> None:
    events = [
        ResponseOutputItemDoneEvent(SimpleNamespace(type="reasoning")),
        ResponseOutputItemDoneEvent(CALL_ITEM),
        ResponseCompletedEvent(response=SimpleNamespace(usage=None)),
    ]
    chunks = list(_instance()._handle_responses_api_stream("openai.gpt-5.5", {}, events, []))
    assert len(chunks) == 2
    [tool_call] = chunks[0].delta.message.tool_calls
    assert (tool_call.id, tool_call.function.name) == ("call_1", "get_weather")
    assert chunks[-1].delta.finish_reason == "stop"
