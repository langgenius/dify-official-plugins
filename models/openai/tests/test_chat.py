from types import SimpleNamespace

import hashlib

import pytest

from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import (
    AudioPromptMessageContent,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeConnectionError,
)
from models.llm import chat


def _delta(*, content=None, refusal=None, tool_calls=None, function_call=None):
    return SimpleNamespace(
        content=content,
        refusal=refusal,
        tool_calls=tool_calls,
        function_call=function_call,
    )


def _chat_chunk(*, delta=None, finish_reason=None, usage=None, model="gpt-4o"):
    choices = (
        []
        if delta is None
        else [SimpleNamespace(index=0, delta=delta, finish_reason=finish_reason)]
    )
    return SimpleNamespace(
        model=model,
        system_fingerprint="fp_chat",
        usage=usage,
        choices=choices,
    )


def _llm(mocker):
    llm = mocker.Mock()
    llm._calc_response_usage.return_value = LLMUsage.empty_usage()
    return llm


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("hello", "hello"),
        (
            [TextPromptMessageContent(data="hello")],
            [{"type": "text", "text": "hello"}],
        ),
        (
            [
                ImagePromptMessageContent(
                    url="https://example.com/cat.png",
                    mime_type="image/png",
                    format="png",
                )
            ],
            [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/cat.png",
                        "detail": "low",
                    },
                }
            ],
        ),
        (
            [
                AudioPromptMessageContent(
                    base64_data="UklGRg==",
                    mime_type="audio/wav",
                    format=".wav",
                )
            ],
            [
                {
                    "type": "input_audio",
                    "input_audio": {"data": "UklGRg==", "format": "wav"},
                }
            ],
        ),
    ],
)
def test_user_message_content(content, expected):
    assert chat.message(UserPromptMessage(content=content)) == {
        "role": "user",
        "content": expected,
    }


def test_chat_rejects_document_content():
    document = DocumentPromptMessageContent(
        url="https://example.com/context.pdf",
        mime_type="application/pdf",
        format="pdf",
    )

    with pytest.raises(InvokeBadRequestError, match="Responses API"):
        chat.message(UserPromptMessage(content=[document]))


@pytest.mark.parametrize(
    ("content", "match"),
    [
        (
            ImagePromptMessageContent(mime_type="image/png", format="png"),
            "Image input must include data",
        ),
        (
            AudioPromptMessageContent(
                url="https://example.com/audio.mp3",
                mime_type="audio/mpeg",
                format="mp3",
            ),
            "Audio input must include base64 data",
        ),
        (
            AudioPromptMessageContent(
                base64_data="T2dnUw==",
                mime_type="audio/ogg",
                format="ogg",
            ),
            "Audio input must be MP3 or WAV",
        ),
    ],
)
def test_chat_rejects_invalid_multimodal_data(content, match):
    with pytest.raises(InvokeBadRequestError, match=match):
        chat.message(UserPromptMessage(content=[content]))


def test_chat_builds_structured_json_schema():
    assert chat._chat_params(
        {
            "response_format": "json_schema",
            "json_schema": '{"type":"object","properties":{"answer":{"type":"string"}}}',
        }
    ) == {
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                },
            },
        }
    }


@pytest.mark.parametrize(
    "model",
    ["gpt-5.6", "o3", "ft:gpt-5-mini:organization:custom"],
)
def test_reasoning_models_use_max_completion_tokens(model):
    assert chat.uses_max_completion_tokens(model)


@pytest.mark.parametrize(
    ("credentials", "expected"),
    [
        (
            {},
            {
                "safety_identifier": hashlib.sha256(b"user-1").hexdigest(),
                "prompt_cache_key": hashlib.sha256(b"user-1").hexdigest(),
            },
        ),
        (
            {"openai_api_base": "https://proxy.example.com"},
            {"user": hashlib.sha256(b"user-1").hexdigest()},
        ),
    ],
)
def test_chat_hashes_user_for_official_and_compatible_endpoints(credentials, expected):
    parameters = {}

    chat._add_identity(parameters, "user-1", credentials)

    assert parameters == expected


@pytest.mark.parametrize(
    "parameter", ["reasoning_summary", "reasoning_mode", "reasoning_context"]
)
def test_chat_rejects_responses_only_reasoning_parameters(parameter):
    with pytest.raises(InvokeBadRequestError, match=parameter):
        chat._chat_params({parameter: "enabled"})


def test_nonstream_chat_returns_refusal_and_tool_call(mocker):
    llm = _llm(mocker)
    client = mocker.Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        model="gpt-4o-2024-11-20",
        system_fingerprint="fp_result",
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    refusal="I cannot help.",
                    function_call=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="lookup", arguments='{"query":"x"}'
                            ),
                        )
                    ],
                ),
            )
        ],
    )

    result = chat.generate_chat(
        llm,
        client,
        "gpt-4o",
        {},
        [UserPromptMessage(content="hello")],
        {},
        None,
        None,
        False,
        None,
    )

    assert result.message.content == "I cannot help."
    assert [call.id for call in result.message.tool_calls] == ["call_1"]
    assert result.message.tool_calls[0].function.name == "lookup"
    assert result.message.tool_calls[0].function.arguments == '{"query":"x"}'
    assert result.system_fingerprint == "fp_result"
    llm._calc_response_usage.assert_called_once_with("gpt-4o", {}, 5, 3)


def test_nonstream_chat_discards_truncated_tool_call(mocker):
    client = mocker.Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        model="gpt-4o",
        system_fingerprint=None,
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
        choices=[
            SimpleNamespace(
                finish_reason="length",
                message=SimpleNamespace(
                    content=None,
                    refusal=None,
                    function_call=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(name="lookup", arguments='{"x":'),
                        )
                    ],
                ),
            )
        ],
    )

    result = chat.generate_chat(
        _llm(mocker),
        client,
        "gpt-4o",
        {},
        [UserPromptMessage(content="hello")],
        {},
        None,
        None,
        False,
        None,
    )

    assert result.message.tool_calls == []


def test_chat_stream_keeps_content_and_refusal_separate(mocker):
    llm = _llm(mocker)
    usage = SimpleNamespace(prompt_tokens=7, completion_tokens=4)
    events = [
        _chat_chunk(delta=_delta(content="answer ")),
        _chat_chunk(delta=_delta(refusal="denied"), finish_reason="stop"),
        _chat_chunk(usage=usage),
    ]
    stream = mocker.MagicMock()
    stream.__iter__.return_value = iter(events)
    client = mocker.Mock()
    client.chat.completions.create.return_value = stream

    chunks = list(
        chat.generate_chat(
            llm,
            client,
            "gpt-4o",
            {},
            [UserPromptMessage(content="hello")],
            {},
            None,
            None,
            True,
            None,
        )
    )

    assert [chunk.delta.message.content for chunk in chunks] == [
        "answer ",
        "denied",
        "",
    ]
    assert chunks[-1].delta.finish_reason == "stop"
    assert sum(chunk.delta.usage is not None for chunk in chunks) == 1
    llm._calc_response_usage.assert_called_once_with("gpt-4o", {}, 7, 4)
    stream.close.assert_called_once_with()


def test_chat_stream_aggregates_interleaved_tool_calls_by_index(mocker):
    llm = _llm(mocker)
    usage = SimpleNamespace(prompt_tokens=9, completion_tokens=6)

    def tool(index, call_id=None, name=None, arguments=None):
        return SimpleNamespace(
            index=index,
            id=call_id,
            function=SimpleNamespace(name=name, arguments=arguments),
        )

    events = [
        _chat_chunk(delta=_delta(tool_calls=[tool(1, "call_b", "beta", '{"b":')])),
        _chat_chunk(delta=_delta(tool_calls=[tool(0, "call_a", "alpha", '{"a":')])),
        _chat_chunk(delta=_delta(tool_calls=[tool(1, arguments="2}")])),
        _chat_chunk(
            delta=_delta(tool_calls=[tool(0, arguments="1}")]),
            finish_reason="tool_calls",
        ),
        _chat_chunk(usage=usage),
    ]
    stream = mocker.MagicMock()
    stream.__iter__.return_value = iter(events)
    client = mocker.Mock()
    client.chat.completions.create.return_value = stream

    chunks = list(
        chat.generate_chat(
            llm,
            client,
            "gpt-4o",
            {},
            [UserPromptMessage(content="hello")],
            {},
            None,
            None,
            True,
            None,
        )
    )

    terminal = [chunk for chunk in chunks if chunk.delta.finish_reason is not None]
    assert len(terminal) == 1
    assert sum(chunk.delta.usage is not None for chunk in chunks) == 1
    assert terminal[0].delta.finish_reason == "tool_calls"
    calls = terminal[0].delta.message.tool_calls
    assert [
        (call.id, call.function.name, call.function.arguments) for call in calls
    ] == [
        ("call_a", "alpha", '{"a":1}'),
        ("call_b", "beta", '{"b":2}'),
    ]
    llm._calc_response_usage.assert_called_once_with("gpt-4o", {}, 9, 6)
    stream.close.assert_called_once_with()


def test_chat_stream_discards_tool_fragment_when_output_is_truncated(mocker):
    fragment = SimpleNamespace(
        index=0,
        id="call_1",
        function=SimpleNamespace(name="lookup", arguments='{"x":'),
    )
    usage = SimpleNamespace(prompt_tokens=7, completion_tokens=4)
    events = [
        _chat_chunk(
            delta=_delta(tool_calls=[fragment]),
            finish_reason="length",
        ),
        _chat_chunk(usage=usage),
    ]
    stream = mocker.MagicMock()
    stream.__iter__.return_value = iter(events)
    client = mocker.Mock()
    client.chat.completions.create.return_value = stream

    chunks = list(
        chat.generate_chat(
            _llm(mocker),
            client,
            "gpt-4o",
            {},
            [UserPromptMessage(content="hello")],
            {},
            None,
            None,
            True,
            None,
        )
    )

    assert chunks[-1].delta.finish_reason == "length"
    assert chunks[-1].delta.message.tool_calls == []


def test_chat_stream_without_finish_reason_raises_and_closes(mocker):
    stream = mocker.MagicMock()
    stream.__iter__.return_value = iter([_chat_chunk(delta=_delta(content="partial"))])
    client = mocker.Mock()
    client.chat.completions.create.return_value = stream

    result = chat.generate_chat(
        _llm(mocker),
        client,
        "gpt-4o",
        {},
        [UserPromptMessage(content="hello")],
        {},
        None,
        None,
        True,
        None,
    )

    with pytest.raises(InvokeConnectionError, match="finish reason"):
        list(result)
    stream.close.assert_called_once_with()


def test_closing_chat_generator_closes_sdk_stream(mocker):
    stream = mocker.MagicMock()
    stream.__iter__.return_value = iter(
        [
            _chat_chunk(delta=_delta(content="first")),
            _chat_chunk(delta=_delta(content="second"), finish_reason="stop"),
        ]
    )
    client = mocker.Mock()
    client.chat.completions.create.return_value = stream
    result = chat.generate_chat(
        _llm(mocker),
        client,
        "gpt-4o",
        {},
        [UserPromptMessage(content="hello")],
        {},
        None,
        None,
        True,
        None,
    )

    assert next(result).delta.message.content == "first"
    result.close()

    stream.close.assert_called_once_with()
