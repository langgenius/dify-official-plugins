import json
import sys
from pathlib import Path

import cohere
import httpx
import pytest
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.llm.llm import CohereLargeLanguageModel


@pytest.mark.parametrize("chat", [True, False])
def test_sdk_stream_events_and_tool_results(chat):
    llm = CohereLargeLanguageModel([])
    llm._num_tokens_from_messages = lambda *args: 1
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    tool_call = {"name": "weather", "parameters": {"city": "Tokyo"}}
    events = [{"event_type": "text-generation", "text": "Hello", "is_finished": False}]
    if chat:
        events.append(
            {"event_type": "tool-calls-generation", "tool_calls": [tool_call]}
        )
    events.append(
        {
            "event_type": "stream-end",
            "is_finished": True,
            "finish_reason": "COMPLETE",
            "response": {"text": "Hello"} if chat else {"id": "generation"},
        }
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, text="\n".join(json.dumps(event) for event in events)
        )
    )
    with cohere.Client(
        "test-key", httpx_client=httpx.Client(transport=transport)
    ) as client:
        if chat:
            response = client.chat_stream(model="command", message="Hi")
            handler = llm._handle_chat_generate_stream_response
        else:
            response = client.generate_stream(model="command", prompt="Hi")
            handler = llm._handle_generate_stream_response
        chunks = list(
            handler("command", {}, response, [UserPromptMessage(content="Hi")])
        )

    assert [chunk.delta.message.content for chunk in chunks] == ["Hello", ""]
    assert chunks[-1].delta.finish_reason == "COMPLETE"
    if chat:
        result_call = chunks[-1].delta.message.tool_calls[0]
        assert result_call.function.name == "weather"
        _, _, results = llm._convert_prompt_messages_to_message_and_chat_histories(
            [
                UserPromptMessage(content="Weather?"),
                AssistantPromptMessage(content="", tool_calls=[result_call]),
                ToolPromptMessage(content="Sunny", tool_call_id=result_call.id),
            ]
        )
        assert isinstance(results[0], cohere.ToolResult)
        assert results[0].model_dump() == {
            "call": tool_call,
            "outputs": [{"result": "Sunny"}],
        }


def test_sdk_generation_stream_error_is_propagated():
    event = {
        "event_type": "stream-error",
        "is_finished": True,
        "finish_reason": "ERROR",
        "err": "generation failed",
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=json.dumps(event))
    )
    with cohere.Client(
        "test-key", httpx_client=httpx.Client(transport=transport)
    ) as client:
        response = client.generate_stream(model="command", prompt="Hi")
        with pytest.raises(InvokeBadRequestError, match="generation failed"):
            list(
                CohereLargeLanguageModel([])._handle_generate_stream_response(
                    "command", {}, response, [UserPromptMessage(content="Hi")]
                )
            )


@pytest.mark.parametrize("stream", [False, True])
def test_same_function_calls_keep_separate_results(stream):
    calls = [
        {"name": "weather", "parameters": {"city": city}} for city in ("Tokyo", "Paris")
    ]
    response = {"text": "", "tool_calls": calls}
    events = [
        {"event_type": "tool-calls-generation", "tool_calls": calls},
        {
            "event_type": "stream-end",
            "is_finished": True,
            "finish_reason": "COMPLETE",
            "response": response,
        },
    ]
    transport = httpx.MockTransport(
        lambda request: (
            httpx.Response(200, text="\n".join(json.dumps(event) for event in events))
            if stream
            else httpx.Response(200, json=response)
        )
    )
    llm = CohereLargeLanguageModel([])
    llm._num_tokens_from_messages = lambda *args: 1
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    with cohere.Client(
        "test-key", httpx_client=httpx.Client(transport=transport)
    ) as client:
        if stream:
            chunks = list(
                llm._handle_chat_generate_stream_response(
                    "command", {}, client.chat_stream(model="command", message="Hi"), []
                )
            )
            result_calls = [
                call for chunk in chunks for call in chunk.delta.message.tool_calls
            ]
        else:
            result_calls = llm._handle_chat_generate_response(
                "command", {}, client.chat(model="command", message="Hi"), []
            ).message.tool_calls

    assert len(result_calls) == 2
    assert all(call.id for call in result_calls)
    assert len({call.id for call in result_calls}) == 2
    _, _, results = llm._convert_prompt_messages_to_message_and_chat_histories(
        [
            UserPromptMessage(content="Weather?"),
            AssistantPromptMessage(content="", tool_calls=result_calls),
            ToolPromptMessage(content="Rain", tool_call_id=result_calls[1].id),
            ToolPromptMessage(content="Sun", tool_call_id=result_calls[0].id),
        ]
    )
    assert [result.model_dump() for result in results] == [
        {"call": calls[0], "outputs": [{"result": "Sun"}]},
        {"call": calls[1], "outputs": [{"result": "Rain"}]},
    ]
