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
