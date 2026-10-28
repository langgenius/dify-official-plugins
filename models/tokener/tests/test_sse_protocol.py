import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import InvokeConnectionError, InvokeServerUnavailableError

from models.llm._sse import ChatCompletionSSEStreamResponse
from models.llm.llm import TokenerLargeLanguageModel, _ToolCallStreamResponse


def _response(body: str | bytes, chunk_size: int = 3):
    raw = body.encode("utf-8") if isinstance(body, str) else body
    response = requests.Response()
    response.status_code = 200
    response.iter_content = Mock(
        return_value=(raw[index : index + chunk_size] for index in range(0, len(raw), chunk_size))
    )
    response.close = Mock()
    return response


def _event(payload: dict, newline: str = "\n") -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + newline * 2


def _choice(content="你好 🦊", finish=None, **extra):
    return {
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish}],
        **extra,
    }


def _read(response):
    adapter = ChatCompletionSSEStreamResponse(response)
    decoded = [
        json.loads(line.removeprefix("data: "))
        for line in adapter.iter_lines(decode_unicode=True, delimiter="\n\n")
    ]
    return adapter, decoded


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("chunk_size", [1, 2, 7, 512])
def test_line_endings_chunk_boundaries_non_ascii_and_usage_are_preserved(newline, chunk_size):
    payloads = [_choice(), _choice("", "stop", usage={"prompt_tokens": 2, "completion_tokens": 3})]
    response = _response(
        "\ufeff"
        + ": keepalive"
        + newline * 2
        + "".join(_event(p, newline) for p in payloads)
        + "data: [DONE]"
        + newline * 2,
        chunk_size,
    )
    adapter, decoded = _read(response)
    assert decoded == payloads
    assert adapter.usage_source == "upstream"
    response.close.assert_called_once()


def test_event_id_retry_and_multiline_data_fields_are_supported():
    payload = _choice("answer", "stop")
    body = (
        "event: message\nid: 17\nretry: 100\n: comment\n"
        'data: {"choices":\n'
        'data: [{"index": 0, "delta": {"content": "answer"}, "finish_reason": "stop"}]}\n\n'
        "data:[DONE]\n\n"
    )
    adapter, decoded = _read(_response(body))
    assert decoded == [payload]
    assert adapter.usage_source == "absent"
    assert "usage" not in decoded[0]


def test_finish_reason_is_valid_terminal_without_done_and_usage_only_tail_is_preserved():
    payloads = [
        _choice("answer", "stop"),
        {"choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0}},
    ]
    adapter, decoded = _read(_response("".join(_event(p) for p in payloads)))
    assert decoded == payloads
    assert adapter.usage_source == "upstream"


def test_done_can_terminate_valid_choice_without_finish_reason():
    _, decoded = _read(_response(_event(_choice()) + "data: [DONE]\n\n"))
    assert decoded == [_choice()]


@pytest.mark.parametrize("tail", [": keepalive", "id: 3", "retry: 100"])
def test_comment_or_metadata_tail_does_not_invalidate_completed_choice(tail):
    payload = _choice("answer", "stop")
    _, decoded = _read(_response(_event(payload) + tail))
    assert decoded == [payload]


@pytest.mark.parametrize(
    "usage,provenance",
    [
        ({}, "absent"),
        ({"prompt_tokens": 1}, "upstream_partial_or_invalid"),
        ({"prompt_tokens": 1, "completion_tokens": None}, "upstream_partial_or_invalid"),
        ({"prompt_tokens": 1, "completion_tokens": -1}, "upstream_partial_or_invalid"),
        ({"prompt_tokens": 1, "completion_tokens": True}, "upstream_partial_or_invalid"),
    ],
)
def test_partial_or_invalid_usage_is_not_labelled_authoritative(usage, provenance):
    payload = _choice("answer", "stop", usage=usage)
    adapter, decoded = _read(_response(_event(payload)))
    assert decoded == [payload]
    assert adapter.usage_source == provenance


def test_byte_mode_yields_complete_utf8_records():
    response = _response(_event(_choice(finish="stop")))
    rows = list(ChatCompletionSSEStreamResponse(response).iter_lines())
    assert isinstance(rows[0], bytes)
    assert json.loads(rows[0].removeprefix(b"data: ")) == _choice(finish="stop")


@pytest.mark.parametrize(
    "body",
    [
        "",
        "data: [DONE]\n\n",
        ": keepalive\n\n",
        _event(_choice()),
        'data: {"choices": []}',
        'data: {"choices": []}\n',
        _event(_choice(finish="stop")) + 'data: {"choices": []}',
    ],
)
def test_empty_or_truncated_stream_raises_typed_error_and_closes(body):
    response = _response(body)
    with pytest.raises(InvokeConnectionError):
        _read(response)
    response.close.assert_called_once()


@pytest.mark.parametrize(
    "body",
    [
        "data: {not-json}\n\n",
        "data: []\n\n",
        "data: null\n\n",
        'data: {"choices": null}\n\n',
        'data: {"choices": [null]}\n\n',
        'data: {"choices": [{}]}\n\ndata: [DONE]\n\n',
        'data: {"choices": [{"finish_reason": null}]}\n\ndata: [DONE]\n\n',
        'data: {"choices": [{"finish_reason": ""}]}\n\ndata: [DONE]\n\n',
        'data: {"choices": [{"delta": null}]}\n\n',
        'data: {"choices": [], "usage": {"completion_tokens": NaN}}\n\n',
        b'data: {"choices": [{"delta": {"content": "\xff"}}]}\n\n',
        b'data: {"choices": []}\n\n\xe4',
    ],
)
def test_malformed_payload_or_utf8_raises_without_echoing_payload(body):
    response = _response(body)
    with pytest.raises(InvokeServerUnavailableError) as raised:
        _read(response)
    assert "not-json" not in str(raised.value)
    response.close.assert_called_once()


@pytest.mark.parametrize(
    "body",
    [
        'data: {"error": {"message": "secret upstream detail"}}\n\n',
        'data: {"choices": [], "error": {"message": "secret upstream detail"}}\n\n',
        'event: error\ndata: {"message": "secret upstream detail"}\n\n',
    ],
)
def test_error_envelope_is_not_swallowed_or_exposed(body):
    with pytest.raises(InvokeServerUnavailableError) as raised:
        _read(_response(body))
    assert "secret upstream detail" not in str(raised.value)


def test_malformed_tail_is_not_reported_as_normal_final():
    response = _response(_event(_choice()) + "data: bad\n\n")
    iterator = ChatCompletionSSEStreamResponse(response).iter_lines(decode_unicode=True)
    assert json.loads(next(iterator).removeprefix("data: ")) == _choice()
    with pytest.raises(InvokeServerUnavailableError):
        next(iterator)


def test_tools_reasoning_and_usage_pass_through_then_accumulate_correctly():
    first = {
        "choices": [
            {
                "delta": {
                    "reasoning_content": "private reasoning",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": '{"x":'},
                        }
                    ],
                },
                "finish_reason": None,
            }
        ]
    }
    last = {
        "choices": [
            {
                "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "1}"}}]},
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 8},
    }
    body = _event(first, "\r\n") + _event(last, "\r\n") + "data: [DONE]\r\n\r\n"
    _, decoded = _read(_response(body))
    assert decoded == [first, last]
    assert "content" not in decoded[0]["choices"][0]["delta"]
    adapted = _ToolCallStreamResponse(ChatCompletionSSEStreamResponse(_response(body)))
    rows = list(adapted.iter_lines(decode_unicode=True, delimiter="\n\n"))
    assert adapted.tool_calls[0].function.arguments == '{"x":1}'
    assert adapted.tool_calls[0].id == "call1"
    assert json.loads(rows[-1].removeprefix("data: "))["usage"] == last["usage"]


def test_request_interruption_is_typed_and_closes():
    response = _response("")
    response.iter_content.side_effect = requests.ConnectionError("secret socket detail")
    with pytest.raises(InvokeConnectionError) as raised:
        _read(response)
    assert "secret socket detail" not in str(raised.value)
    response.close.assert_called_once()


def test_consumer_cancellation_closes_underlying_response():
    response = _response(_event(_choice()) + _event(_choice("", "stop")))
    iterator = ChatCompletionSSEStreamResponse(response).iter_lines(decode_unicode=True)
    next(iterator)
    iterator.close()
    response.close.assert_called_once()


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_normalized_response_is_compatible_with_actual_sdk_parser(newline):
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text())
    )
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    payloads = [
        _choice("你好 FORWARDING_OK"),
        _choice("", "stop", usage={"prompt_tokens": 20, "completion_tokens": 7}),
    ]
    response = _response("".join(_event(payload, newline) for payload in payloads))
    with model.timing_context():
        chunks = list(
            OAICompatLargeLanguageModel._handle_generate_stream_response(
                model,
                schema.model,
                {"mode": "chat"},
                ChatCompletionSSEStreamResponse(response),
                [UserPromptMessage(content="Reply FORWARDING_OK")],
            )
        )
    assert (
        "".join(chunk.delta.message.get_text_content() for chunk in chunks) == "你好 FORWARDING_OK"
    )
    assert chunks[-1].delta.finish_reason == "stop"
    assert chunks[-1].delta.usage.prompt_tokens == 20
    assert chunks[-1].delta.usage.completion_tokens == 7


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("tool_schema", [False, True])
def test_public_plugin_invoke_normalizes_both_tool_and_plain_streams(newline, tool_schema):
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text())
    )
    if not tool_schema:
        schema = schema.model_copy(update={"features": []})
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    response = _response(
        _event(_choice("你好 FORWARDING_OK"), newline)
        + _event(_choice("", "stop", usage={"prompt_tokens": 20, "completion_tokens": 7}), newline)
    )
    with patch("requests.post", return_value=response) as post:
        chunks = list(
            model.invoke(
                schema.model,
                {"api_key": "offline-test"},
                [UserPromptMessage(content="Reply FORWARDING_OK")],
                {"max_tokens": 256},
                stream=True,
            )
        )
    post.assert_called_once()
    assert (
        "".join(chunk.delta.message.get_text_content() for chunk in chunks) == "你好 FORWARDING_OK"
    )
    assert chunks[-1].delta.usage.completion_tokens == 7
    response.close.assert_called_once()


@pytest.mark.parametrize(
    "error", [InvokeConnectionError("truncated"), InvokeServerUnavailableError("malformed")]
)
def test_plugin_error_transform_preserves_typed_protocol_error(error):
    model = TokenerLargeLanguageModel(model_schemas=[])
    assert model._transform_invoke_error(error) is error


def test_public_invoke_rejects_empty_choice_before_done_instead_of_empty_success():
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text())
    )
    model = TokenerLargeLanguageModel(model_schemas=[schema])
    response = _response(
        _event({"choices": [{}], "usage": {"prompt_tokens": 1, "completion_tokens": 0}})
        + "data: [DONE]\n\n"
    )
    with patch("requests.post", return_value=response):
        with pytest.raises(InvokeServerUnavailableError):
            list(
                model.invoke(
                    schema.model,
                    {"api_key": "offline-test"},
                    [UserPromptMessage(content="Reply FORWARDING_OK")],
                    {"max_tokens": 256},
                    stream=True,
                )
            )
    response.close.assert_called_once()
