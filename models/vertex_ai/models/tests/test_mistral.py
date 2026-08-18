import os
import sys

from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from mistralai.gcp.client.models import (
    AssistantMessage,
    ChatCompletionChoice,
    ChatCompletionResponse,
    CompletionChunk,
    CompletionEvent,
    CompletionResponseStreamChoice,
    DeltaMessage,
    FunctionCall,
    ToolCall,
    UsageInfo,
)

try:
    from models.llm.llm import VertexAiLargeLanguageModel, _normalize_mistral_tool_call_id
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from models.llm.llm import VertexAiLargeLanguageModel, _normalize_mistral_tool_call_id


FAKE_USAGE = LLMUsage(
    prompt_tokens=0,
    prompt_unit_price=0,
    prompt_price_unit=0,
    prompt_price=0,
    completion_tokens=0,
    completion_unit_price=0,
    completion_price_unit=0,
    completion_price=0,
    total_tokens=0,
    total_price=0,
    currency="USD",
    latency=0,
)


def _llm():
    llm = VertexAiLargeLanguageModel([])
    llm._calc_response_usage = lambda *args, **kwargs: FAKE_USAGE
    return llm


def test_normalize_mistral_tool_call_id_rejects_null_sentinel():
    # The mistralai-gcp SDK defaults an omitted id to the literal string "null".
    assert _normalize_mistral_tool_call_id("null", "get_weather") == "get_weather"
    assert _normalize_mistral_tool_call_id("", "get_weather") == "get_weather"
    assert _normalize_mistral_tool_call_id(None, "get_weather") == "get_weather"
    assert _normalize_mistral_tool_call_id("call_123", "get_weather") == "call_123"


def test_convert_system_and_user_text_messages():
    llm = _llm()
    assert llm._convert_mistral_prompt_message_to_dict(SystemPromptMessage(content="be nice")) == {
        "role": "system",
        "content": "be nice",
    }
    assert llm._convert_mistral_prompt_message_to_dict(UserPromptMessage(content="hi")) == {
        "role": "user",
        "content": "hi",
    }


def test_convert_user_message_with_image_content():
    llm = _llm()
    message = UserPromptMessage(
        content=[
            ImagePromptMessageContent(url="https://example.com/cat.png", format="png", mime_type="image/png"),
        ]
    )
    result = llm._convert_mistral_prompt_message_to_dict(message)
    assert result["role"] == "user"
    assert result["content"] == [{"type": "image_url", "image_url": {"url": "https://example.com/cat.png"}}]


def test_convert_assistant_message_with_tool_calls():
    llm = _llm()
    message = AssistantPromptMessage(
        content="",
        tool_calls=[
            AssistantPromptMessage.ToolCall(
                id="call_1",
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name="get_weather", arguments='{"city": "Tokyo"}'
                ),
            )
        ],
    )
    result = llm._convert_mistral_prompt_message_to_dict(message)
    assert result == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'}}
        ],
    }


def test_convert_tool_message():
    llm = _llm()
    message = ToolPromptMessage(content='{"temp": 20}', tool_call_id="call_1", name="get_weather")
    assert llm._convert_mistral_prompt_message_to_dict(message) == {
        "role": "tool",
        "content": '{"temp": 20}',
        "tool_call_id": "call_1",
        "name": "get_weather",
    }


def test_convert_tools():
    llm = _llm()
    tool = PromptMessageTool(
        name="get_weather",
        description="Get the weather for a city",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    )
    assert llm._convert_mistral_tools([tool]) == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather for a city",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            },
        }
    ]


def test_non_streaming_response_falls_back_to_function_name_when_id_is_omitted():
    # Regression test: ToolCall.id defaults to the literal string "null" (not None) when the
    # API omits it, and must not be surfaced as a real id.
    llm = _llm()
    response = ChatCompletionResponse(
        id="resp_1",
        object="chat.completion",
        model="mistral-small-2503",
        created=0,
        usage=UsageInfo(prompt_tokens=3, completion_tokens=4, total_tokens=7),
        choices=[
            ChatCompletionChoice(
                index=0,
                finish_reason="tool_calls",
                message=AssistantMessage(
                    content=None,
                    tool_calls=[ToolCall(function=FunctionCall(name="get_weather", arguments='{"city": "Tokyo"}'))],
                ),
            )
        ],
    )

    result = llm._handle_mistral_response("mistral-small-2503", {}, response, [])

    assert result.message.content == ""
    assert len(result.message.tool_calls) == 1
    assert result.message.tool_calls[0].id == "get_weather"
    assert result.message.tool_calls[0].function.name == "get_weather"
    assert result.message.tool_calls[0].function.arguments == '{"city": "Tokyo"}'


def test_non_streaming_response_keeps_real_tool_call_id():
    llm = _llm()
    response = ChatCompletionResponse(
        id="resp_1",
        object="chat.completion",
        model="mistral-small-2503",
        created=0,
        usage=UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        choices=[
            ChatCompletionChoice(
                index=0,
                finish_reason="tool_calls",
                message=AssistantMessage(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_9", function=FunctionCall(name="get_weather", arguments="{}"))
                    ],
                ),
            )
        ],
    )

    result = llm._handle_mistral_response("mistral-small-2503", {}, response, [])

    assert result.message.tool_calls[0].id == "call_9"


def _stream_event(*, index=0, content=None, tool_calls=None, finish_reason=None, usage=None):
    return CompletionEvent(
        data=CompletionChunk(
            id="1",
            model="mistral-small-2503",
            usage=usage,
            choices=[
                CompletionResponseStreamChoice(
                    index=index,
                    delta=DeltaMessage(content=content, tool_calls=tool_calls),
                    finish_reason=finish_reason,
                )
            ],
        )
    )


def test_streaming_text_deltas_are_yielded_incrementally():
    llm = _llm()
    stream = [
        _stream_event(content="Hel"),
        _stream_event(content="lo"),
        _stream_event(finish_reason="stop", usage=UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3)),
    ]

    chunks = list(llm._handle_mistral_stream_response("mistral-small-2503", {}, stream, []))

    assert [c.delta.message.content for c in chunks] == ["Hel", "lo", ""]
    assert chunks[-1].delta.finish_reason == "stop"
    assert chunks[-1].delta.message.tool_calls == []


def test_streaming_reassembles_tool_call_split_across_multiple_chunks():
    llm = _llm()
    stream = [
        _stream_event(
            tool_calls=[
                ToolCall(id="call_1", index=0, function=FunctionCall(name="get_weather", arguments='{"cit'))
            ]
        ),
        _stream_event(
            tool_calls=[ToolCall(index=0, function=FunctionCall(name="get_weather", arguments='y": "Tokyo"}'))],
            finish_reason="tool_calls",
            usage=UsageInfo(prompt_tokens=5, completion_tokens=6, total_tokens=11),
        ),
    ]

    chunks = list(llm._handle_mistral_stream_response("mistral-small-2503", {}, stream, []))

    assert len(chunks) == 1
    tool_calls = chunks[-1].delta.message.tool_calls
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "call_1"
    assert tool_calls[0].function.arguments == '{"city": "Tokyo"}'


def test_streaming_handles_parallel_tool_calls_independently():
    llm = _llm()
    stream = [
        _stream_event(
            tool_calls=[
                ToolCall(id="call_1", index=0, function=FunctionCall(name="get_weather", arguments='{"city": "Tokyo"}')),
                ToolCall(id="call_2", index=1, function=FunctionCall(name="get_time", arguments='{"tz": "JST"}')),
            ],
            finish_reason="tool_calls",
            usage=UsageInfo(prompt_tokens=5, completion_tokens=6, total_tokens=11),
        ),
    ]

    chunks = list(llm._handle_mistral_stream_response("mistral-small-2503", {}, stream, []))

    tool_calls = {tc.id: tc for tc in chunks[-1].delta.message.tool_calls}
    assert set(tool_calls) == {"call_1", "call_2"}
    assert tool_calls["call_1"].function.name == "get_weather"
    assert tool_calls["call_1"].function.arguments == '{"city": "Tokyo"}'
    assert tool_calls["call_2"].function.name == "get_time"
    assert tool_calls["call_2"].function.arguments == '{"tz": "JST"}'


def test_streaming_null_sentinel_does_not_clobber_a_real_id_from_an_earlier_fragment():
    llm = _llm()
    stream = [
        _stream_event(
            tool_calls=[
                ToolCall(id="call_1", index=0, function=FunctionCall(name="get_weather", arguments='{"cit'))
            ]
        ),
        # A later fragment for the same tool call omits the id; the SDK defaults it to "null".
        _stream_event(
            tool_calls=[ToolCall(index=0, function=FunctionCall(name="get_weather", arguments='y": "Tokyo"}'))],
            finish_reason="tool_calls",
            usage=UsageInfo(prompt_tokens=5, completion_tokens=6, total_tokens=11),
        ),
    ]

    chunks = list(llm._handle_mistral_stream_response("mistral-small-2503", {}, stream, []))

    assert chunks[-1].delta.message.tool_calls[0].id == "call_1"
