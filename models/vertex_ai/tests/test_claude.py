import base64
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import anthropic
import httpx2
import pytest
import requests
from anthropic import AnthropicVertex
import yaml
from anthropic.types import (
    InputJSONDelta,
    Message,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStopEvent,
    SignatureDelta,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
    ToolUseBlock,
    Usage,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm import llm

MODEL = "claude-sonnet-5"
CREDENTIALS = {"vertex_project_id": "test-project", "vertex_location": "us-east5"}
TOOL = PromptMessageTool(
    name="get_weather",
    description="Get the weather",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}},
)


def _message(content, stop_reason="end_turn"):
    return Message(
        id="msg_1",
        type="message",
        role="assistant",
        model=MODEL,
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def _mock_client(monkeypatch, final_message=None, events=()):
    stream = SimpleNamespace(get_final_message=Mock(return_value=final_message))

    @contextmanager
    def stream_ctx(**kwargs):
        yield stream

    messages = SimpleNamespace(
        create=Mock(return_value=iter(events)),
        stream=Mock(side_effect=stream_ctx),
    )
    client = SimpleNamespace(messages=messages)
    vertex = Mock(return_value=client)
    monkeypatch.setattr(llm, "AnthropicVertex", vertex)
    return vertex, messages


@pytest.mark.parametrize("name", ["sonnet-5", "opus-4-7", "opus-4-8"])
def test_no_sampling_parameter_rules(name):
    path = Path(__file__).parents[1] / f"models/llm/anthropic.claude-{name}.yaml"
    rules = {r["name"] for r in yaml.safe_load(path.read_text())["parameter_rules"]}
    assert not {"temperature", "top_p", "top_k"} & rules


def test_missing_anthropic_location_falls_back(monkeypatch):
    vertex, _ = _mock_client(monkeypatch, final_message=_message([TextBlock(type="text", text="hi")]))
    model = llm.VertexAiLargeLanguageModel([])
    model._generate_anthropic(MODEL, CREDENTIALS, [UserPromptMessage(content="Hi")], {"max_tokens": 10}, stream=False)
    assert vertex.call_args.kwargs["region"] == "us-east5"


def test_anthropic_location_overrides(monkeypatch):
    vertex, _ = _mock_client(monkeypatch, final_message=_message([TextBlock(type="text", text="hi")]))
    model = llm.VertexAiLargeLanguageModel([])
    credentials = {**CREDENTIALS, "vertex_anthropic_location": "global"}
    model._generate_anthropic(MODEL, credentials, [UserPromptMessage(content="Hi")], {"max_tokens": 10}, stream=False)
    assert vertex.call_args.kwargs["region"] == "global"


def test_non_stream_uses_streaming_and_skips_thinking(monkeypatch):
    final = _message(
        [
            ThinkingBlock(type="thinking", thinking="", signature="sig"),
            TextBlock(type="text", text="Let me check."),
            ToolUseBlock(type="tool_use", id="toolu_1", name="get_weather", input={"city": "Tokyo"}),
        ],
        stop_reason="tool_use",
    )
    _, messages = _mock_client(monkeypatch, final_message=final)
    model = llm.VertexAiLargeLanguageModel([])
    result = model._generate_anthropic(
        MODEL, CREDENTIALS, [UserPromptMessage(content="Weather?")], {"max_tokens": 128000}, [TOOL], stream=False
    )
    messages.create.assert_not_called()
    assert messages.stream.call_args.kwargs["max_tokens"] == 128000
    assert messages.stream.call_args.kwargs["tools"] == [
        {"name": "get_weather", "description": "Get the weather", "input_schema": TOOL.parameters}
    ]
    assert result.message.content == "Let me check."
    assert len(result.message.tool_calls) == 1
    tool_call = result.message.tool_calls[0]
    assert tool_call.id == "toolu_1"
    assert tool_call.function.name == "get_weather"
    assert json.loads(tool_call.function.arguments) == {"city": "Tokyo"}


def test_stream_skips_thinking_and_collects_tool_calls(monkeypatch):
    events = [
        RawMessageStartEvent(type="message_start", message=_message([])),
        RawContentBlockStartEvent(
            type="content_block_start", index=0, content_block=ThinkingBlock(type="thinking", thinking="", signature="")
        ),
        RawContentBlockDeltaEvent(
            type="content_block_delta", index=0, delta=ThinkingDelta(type="thinking_delta", thinking="")
        ),
        RawContentBlockDeltaEvent(
            type="content_block_delta", index=0, delta=SignatureDelta(type="signature_delta", signature="sig")
        ),
        RawContentBlockStopEvent(type="content_block_stop", index=0),
        RawContentBlockStartEvent(type="content_block_start", index=1, content_block=TextBlock(type="text", text="")),
        RawContentBlockDeltaEvent(type="content_block_delta", index=1, delta=TextDelta(type="text_delta", text="Hello")),
        RawContentBlockStopEvent(type="content_block_stop", index=1),
        RawContentBlockStartEvent(
            type="content_block_start",
            index=2,
            content_block=ToolUseBlock(type="tool_use", id="toolu_1", name="get_weather", input={}),
        ),
        RawContentBlockDeltaEvent(
            type="content_block_delta",
            index=2,
            delta=InputJSONDelta(type="input_json_delta", partial_json='{"city": '),
        ),
        RawContentBlockDeltaEvent(
            type="content_block_delta",
            index=2,
            delta=InputJSONDelta(type="input_json_delta", partial_json='"Tokyo"}'),
        ),
        RawContentBlockStopEvent(type="content_block_stop", index=2),
        RawMessageDeltaEvent(
            type="message_delta",
            delta={"stop_reason": "tool_use", "stop_sequence": None},
            usage={"output_tokens": 5},
        ),
        RawMessageStopEvent(type="message_stop"),
    ]
    _mock_client(monkeypatch, events=events)
    model = llm.VertexAiLargeLanguageModel([])
    chunks = list(
        model._generate_anthropic(
            MODEL, CREDENTIALS, [UserPromptMessage(content="Weather?")], {"max_tokens": 100}, [TOOL], stream=True
        )
    )
    assert "".join(c.delta.message.content for c in chunks) == "Hello"
    final = chunks[-1].delta
    assert final.finish_reason == "tool_use"
    assert [(t.id, t.function.name) for t in final.message.tool_calls] == [("toolu_1", "get_weather")]
    assert json.loads(final.message.tool_calls[0].function.arguments) == {"city": "Tokyo"}


def test_tool_round_trip_messages():
    model = llm.VertexAiLargeLanguageModel([])
    tool_calls = [
        AssistantPromptMessage.ToolCall(
            id=f"toolu_{i}",
            type="function",
            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                name="get_weather", arguments=json.dumps({"city": city})
            ),
        )
        for i, city in enumerate(["Tokyo", "Osaka"])
    ]
    prompt_messages = [
        SystemPromptMessage(content="Be brief."),
        UserPromptMessage(content="Weather?"),
        AssistantPromptMessage(content="", tool_calls=tool_calls),
        ToolPromptMessage(content="Sunny", tool_call_id="toolu_0", name="get_weather"),
        ToolPromptMessage(content="Rainy", tool_call_id="toolu_1", name="get_weather"),
    ]
    kwargs = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10}, [TOOL])
    assert kwargs["system"] == "Be brief."
    assert kwargs["messages"] == [
        {"role": "user", "content": "Weather?"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_0", "name": "get_weather", "input": {"city": "Tokyo"}},
                {"type": "tool_use", "id": "toolu_1", "name": "get_weather", "input": {"city": "Osaka"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_0", "content": "Sunny"},
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "Rainy"},
            ],
        },
    ]
    # Thinking blocks from the tool_use turn can't be replayed, so thinking is off here.
    assert kwargs["thinking"] == {"type": "disabled"}


def test_thinking_left_default_without_tool_results():
    model = llm.VertexAiLargeLanguageModel([])
    kwargs = model._build_claude_request_kwargs(MODEL, [UserPromptMessage(content="Hi")], {"max_tokens": 10}, [TOOL])
    assert "thinking" not in kwargs


def _document(mime_type, data, filename="file"):
    return DocumentPromptMessageContent(
        format=filename.rsplit(".", 1)[-1],
        mime_type=mime_type,
        base64_data=base64.b64encode(data).decode(),
        filename=filename,
    )


def _user(*contents):
    return UserPromptMessage(content=[*contents, TextPromptMessageContent(data="Summarize")])


def test_pdf_and_text_documents_are_sent():
    model = llm.VertexAiLargeLanguageModel([])
    pdf = _document("application/pdf", b"%PDF-1.7", "report.pdf")
    txt = _document("text/markdown", "# 見出し".encode(), "notes.md")
    kwargs = model._build_claude_request_kwargs(MODEL, [_user(pdf, txt)], {"max_tokens": 10})
    content = kwargs["messages"][0]["content"]
    assert content[0] == {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf.base64_data},
        "title": "report.pdf",
    }
    assert content[1] == {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": "# 見出し"},
        "title": "notes.md",
    }
    assert content[2] == {"type": "text", "text": "Summarize"}


def _mock_fetch(monkeypatch, chunks=(b"%PDF-1.7",), headers=None, address="10.0.0.5", is_redirect=False):
    response = Mock(headers=headers or {}, is_redirect=is_redirect, raise_for_status=Mock())
    response.iter_content = Mock(return_value=iter(chunks))
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    get = Mock(return_value=response)
    monkeypatch.setattr(llm.requests, "get", get)
    monkeypatch.setattr(llm.socket, "getaddrinfo", Mock(return_value=[(None, None, None, None, (address, 0))]))
    return get


def _url_document(url="https://files.example/report.pdf?sig=secret"):
    return DocumentPromptMessageContent(format="pdf", mime_type="application/pdf", url=url)


def test_document_fetched_from_url(monkeypatch):
    # Dify's own file URLs often resolve to a private address, which must stay reachable.
    get = _mock_fetch(monkeypatch, chunks=(b"%PDF", b"-1.7"))
    model = llm.VertexAiLargeLanguageModel([])
    kwargs = model._build_claude_request_kwargs(MODEL, [_user(_url_document())], {"max_tokens": 10})
    assert get.call_args.args[0] == "https://files.example/report.pdf?sig=secret"
    assert get.call_args.kwargs["allow_redirects"] is False
    assert kwargs["messages"][0]["content"][0]["source"]["data"] == base64.b64encode(b"%PDF-1.7").decode()


@pytest.mark.parametrize(
    ("url", "fetch_kwargs", "message"),
    [
        ("file:///etc/passwd", {}, "Unsupported attachment url"),
        ("http://metadata.example/token?sig=secret", {"address": "169.254.169.254"}, "link-local"),
        ("http://metadata.example/token?sig=secret", {"address": "::ffff:169.254.169.254"}, "link-local"),
        ("http://metadata.example/token?sig=secret", {"address": "fe80::1%en0"}, "link-local"),
        ("http://metadata.example/token?sig=secret", {"address": "fd00:ec2::254"}, "metadata"),
        ("http://metadata.example/token?sig=secret", {"address": "100.100.100.200"}, "metadata"),
        ("http://metadata.example/token?sig=secret", {"address": "::ffff:100.100.100.200"}, "metadata"),
        ("http://metadata.example/token?sig=secret", {"address": "64:ff9b::a9fe:a9fe"}, "metadata"),
        ("http://metadata.example/token?sig=secret", {"address": "2002:a9fe:a9fe::"}, "metadata"),
        ("https://files.example/a.pdf?sig=secret", {"headers": {"Content-Length": str(30 * 1024 * 1024)}}, "larger than"),
        ("https://files.example/a.pdf?sig=secret", {"chunks": [b"x" * (11 * 1024 * 1024)] * 2}, "larger than"),
    ],
)
def test_document_url_fetch_is_restricted(monkeypatch, url, fetch_kwargs, message):
    _mock_fetch(monkeypatch, **fetch_kwargs)
    model = llm.VertexAiLargeLanguageModel([])
    with pytest.raises(InvokeBadRequestError, match=message) as error:
        model._build_claude_request_kwargs(MODEL, [_user(_url_document(url))], {"max_tokens": 10})
    assert "secret" not in str(error.value)


def _mock_redirects(monkeypatch, locations, addresses):
    """Serve a redirect for each location, then the document; resolve hosts from `addresses`."""
    responses = []
    for location in locations:
        redirect = Mock(headers={"Location": location}, is_redirect=True)
        redirect.__enter__ = Mock(return_value=redirect)
        redirect.__exit__ = Mock(return_value=False)
        responses.append(redirect)
    final = Mock(headers={}, is_redirect=False, raise_for_status=Mock())
    final.iter_content = Mock(return_value=iter([b"%PDF-1.7"]))
    final.__enter__ = Mock(return_value=final)
    final.__exit__ = Mock(return_value=False)
    responses.append(final)
    get = Mock(side_effect=responses)
    monkeypatch.setattr(llm.requests, "get", get)
    monkeypatch.setattr(
        llm.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, (addresses[host], 0))]
    )
    return get


def test_document_url_follows_safe_redirects(monkeypatch):
    get = _mock_redirects(
        monkeypatch,
        ["https://cdn.example/report.pdf", "/final.pdf"],
        {"files.example": "203.0.113.1", "cdn.example": "203.0.113.2"},
    )
    model = llm.VertexAiLargeLanguageModel([])
    kwargs = model._build_claude_request_kwargs(MODEL, [_user(_url_document())], {"max_tokens": 10})
    assert [c.args[0] for c in get.call_args_list] == [
        "https://files.example/report.pdf?sig=secret",
        "https://cdn.example/report.pdf",
        "https://cdn.example/final.pdf",
    ]
    assert kwargs["messages"][0]["content"][0]["type"] == "document"


def test_document_url_redirect_to_metadata_is_refused(monkeypatch):
    get = _mock_redirects(
        monkeypatch,
        ["http://metadata.internal/computeMetadata/v1/"],
        {"files.example": "203.0.113.1", "metadata.internal": "169.254.169.254"},
    )
    model = llm.VertexAiLargeLanguageModel([])
    with pytest.raises(InvokeBadRequestError, match="link-local"):
        model._build_claude_request_kwargs(MODEL, [_user(_url_document())], {"max_tokens": 10})
    assert get.call_count == 1


def test_document_url_too_many_redirects(monkeypatch):
    _mock_redirects(monkeypatch, ["https://files.example/loop"] * 4, {"files.example": "203.0.113.1"})
    model = llm.VertexAiLargeLanguageModel([])
    with pytest.raises(InvokeBadRequestError, match="too many times"):
        model._build_claude_request_kwargs(MODEL, [_user(_url_document())], {"max_tokens": 10})


def test_image_url_fetch_uses_the_same_guard(monkeypatch):
    _mock_fetch(monkeypatch, address="169.254.169.254")
    image = ImagePromptMessageContent(format="png", mime_type="image/png", url="http://metadata.internal/a.png")
    model = llm.VertexAiLargeLanguageModel([])
    with pytest.raises(InvokeBadRequestError, match="link-local"):
        model._build_claude_request_kwargs(MODEL, [_user(image)], {"max_tokens": 10})


def test_total_attachment_size_is_bounded(monkeypatch):
    monkeypatch.setattr(llm, "CLAUDE_MAX_REQUEST_ATTACHMENT_BYTES", 30)
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [
        _user(_document("application/pdf", b"%PDF-1.7 first")),
        AssistantPromptMessage(content="Done"),
        _user(_document("application/pdf", b"%PDF-1.7 second")),
    ]
    with pytest.raises(InvokeBadRequestError, match="add up to more than"):
        model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})


def test_document_url_fetch_failure_hides_query(monkeypatch):
    get = _mock_fetch(monkeypatch)
    get.return_value.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
    model = llm.VertexAiLargeLanguageModel([])
    with pytest.raises(InvokeBadRequestError, match="Failed to fetch attachment") as error:
        model._build_claude_request_kwargs(MODEL, [_user(_url_document())], {"max_tokens": 10})
    assert "secret" not in str(error.value)


def test_oversized_or_invalid_base64_document_raises(monkeypatch):
    model = llm.VertexAiLargeLanguageModel([])
    monkeypatch.setattr(llm, "CLAUDE_MAX_DOCUMENT_BYTES", 4)
    with pytest.raises(InvokeBadRequestError, match="larger than"):
        model._build_claude_request_kwargs(MODEL, [_user(_document("application/pdf", b"%PDF-1.7"))], {"max_tokens": 10})
    monkeypatch.setattr(llm, "CLAUDE_MAX_DOCUMENT_BYTES", 1024)
    broken = DocumentPromptMessageContent(format="pdf", mime_type="application/pdf", base64_data="not base64!")
    with pytest.raises(InvokeBadRequestError, match="Invalid base64"):
        model._build_claude_request_kwargs(MODEL, [_user(broken)], {"max_tokens": 10})


def test_shift_jis_text_document_is_decoded():
    model = llm.VertexAiLargeLanguageModel([])
    text = "日本語の議事録です。来週の定例会議では、予算と採用計画について議論します。"
    doc = _document("text/plain", text.encode("shift_jis"), "minutes.txt")
    kwargs = model._build_claude_request_kwargs(MODEL, [_user(doc)], {"max_tokens": 10})
    assert kwargs["messages"][0]["content"][0]["source"]["data"] == text


def test_text_csv_document_is_accepted():
    model = llm.VertexAiLargeLanguageModel([])
    doc = _document("text/csv", "a,b\n1,2\n".encode(), "data.csv")
    kwargs = model._build_claude_request_kwargs(MODEL, [_user(doc)], {"max_tokens": 10})
    assert kwargs["messages"][0]["content"][0]["source"] == {
        "type": "text",
        "media_type": "text/plain",
        "data": "a,b\n1,2\n",
    }


def test_unsupported_document_in_latest_turn_raises():
    model = llm.VertexAiLargeLanguageModel([])
    docx = _document("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK", "a.docx")
    with pytest.raises(InvokeBadRequestError):
        model._build_claude_request_kwargs(MODEL, [_user(docx)], {"max_tokens": 10})


def test_unsupported_document_in_history_becomes_placeholder():
    model = llm.VertexAiLargeLanguageModel([])
    docx = _document("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK", "a.docx")
    prompt_messages = [
        _user(docx),
        AssistantPromptMessage(content="I can't read that."),
        UserPromptMessage(content="OK, never mind."),
    ]
    kwargs = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})
    assert kwargs["messages"][0]["content"][0] == {
        "type": "text",
        "text": "[Unsupported document: a.docx (application/vnd.openxmlformats-officedocument.wordprocessingml.document)]",
    }


def _stream_events(*blocks, stop_reason="end_turn"):
    """Build a realistic event stream; each block is ("text", str) or ("tool", id, name, [json fragments])."""
    events = [RawMessageStartEvent(type="message_start", message=_message([]))]
    for index, block in enumerate(blocks):
        if block[0] == "text":
            start = TextBlock(type="text", text="")
            deltas = [TextDelta(type="text_delta", text=block[1])]
        else:
            start = ToolUseBlock(type="tool_use", id=block[1], name=block[2], input={})
            deltas = [InputJSONDelta(type="input_json_delta", partial_json=part) for part in block[3]]
        events.append(RawContentBlockStartEvent(type="content_block_start", index=index, content_block=start))
        events.extend(RawContentBlockDeltaEvent(type="content_block_delta", index=index, delta=d) for d in deltas)
        events.append(RawContentBlockStopEvent(type="content_block_stop", index=index))
    events.append(
        RawMessageDeltaEvent(
            type="message_delta",
            delta={"stop_reason": stop_reason, "stop_sequence": None},
            usage={"output_tokens": 5},
        )
    )
    events.append(RawMessageStopEvent(type="message_stop"))
    return events


def _stream(monkeypatch, events):
    _mock_client(monkeypatch, events=events)
    model = llm.VertexAiLargeLanguageModel([])
    return model._generate_anthropic(
        MODEL, CREDENTIALS, [UserPromptMessage(content="Hi")], {"max_tokens": 100}, [TOOL], stream=True
    )


def test_stream_text_only_final_chunk(monkeypatch):
    chunks = list(_stream(monkeypatch, _stream_events(("text", "Hello"))))
    final = chunks[-1].delta
    assert final.message.tool_calls == []
    assert final.finish_reason == "end_turn"
    assert (final.usage.prompt_tokens, final.usage.completion_tokens) == (10, 5)


def test_stream_tool_without_input_deltas_and_trailing_text(monkeypatch):
    events = _stream_events(("tool", "toolu_1", "get_time", []), ("text", "after"), stop_reason="tool_use")
    chunks = list(_stream(monkeypatch, events))
    assert "".join(c.delta.message.content for c in chunks) == "after"
    assert chunks[-1].delta.message.tool_calls[0].function.arguments == "{}"


@pytest.mark.parametrize("stream", [True, False])
def test_tool_call_cut_off_by_max_tokens_raises(monkeypatch, stream):
    model = llm.VertexAiLargeLanguageModel([])
    if stream:
        _mock_client(monkeypatch, events=_stream_events(("tool", "toolu_1", "get_weather", ['{"city": "To']), stop_reason="max_tokens"))
    else:
        final = _message(
            [ToolUseBlock(type="tool_use", id="toolu_1", name="get_weather", input={"city": "To"})],
            stop_reason="max_tokens",
        )
        _mock_client(monkeypatch, final_message=final)
    with pytest.raises(InvokeBadRequestError, match="max_tokens"):
        result = model._generate_anthropic(
            MODEL, CREDENTIALS, [UserPromptMessage(content="Hi")], {"max_tokens": 100}, [TOOL], stream=stream
        )
        if stream:
            list(result)


def _vertex_status_error(status, error_type):
    """Build the error the real Vertex client raises, e.g. for an SSE `error` event inside an HTTP 200 stream."""
    client = AnthropicVertex(region="global", project_id="test-project", access_token="token")
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://example.invalid"))
    body = {"type": "error", "error": {"type": error_type, "message": "Overloaded"}} if error_type else None
    return client._make_status_error(f"{body}", body=body, response=response)


@pytest.mark.parametrize(
    ("status", "error_type", "invoke_error"),
    [
        (200, "overloaded_error", llm.InvokeServerUnavailableError),
        (200, "rate_limit_error", llm.InvokeRateLimitError),
        (200, "invalid_request_error", llm.InvokeBadRequestError),
        (413, None, llm.InvokeBadRequestError),
    ],
)
def test_plain_vertex_status_errors_are_classified(status, error_type, invoke_error):
    error = _vertex_status_error(status, error_type)
    assert type(error) is anthropic.APIStatusError
    assert type(llm.VertexAiLargeLanguageModel([])._transform_invoke_error(error)) is invoke_error


def test_mid_stream_api_error_keeps_its_type(monkeypatch):
    def failing_events():
        yield RawMessageStartEvent(type="message_start", message=_message([]))
        raise _vertex_status_error(200, "overloaded_error")

    model = llm.VertexAiLargeLanguageModel([])
    with pytest.raises(llm.InvokeServerUnavailableError):
        list(model._handle_claude_stream_response(MODEL, CREDENTIALS, failing_events(), []))


@pytest.mark.parametrize(
    ("status", "error_class", "invoke_error"),
    [
        (400, anthropic.BadRequestError, llm.InvokeBadRequestError),
        (401, anthropic.AuthenticationError, llm.InvokeAuthorizationError),
        (403, anthropic.PermissionDeniedError, llm.InvokeBadRequestError),
        (429, anthropic.RateLimitError, llm.InvokeRateLimitError),
        (503, anthropic.ServiceUnavailableError, llm.InvokeServerUnavailableError),
        (500, anthropic.InternalServerError, llm.InvokeServerUnavailableError),
    ],
)
def test_anthropic_errors_are_mapped(status, error_class, invoke_error):
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://example.invalid"))
    error = error_class("Project is not allowed to use this model", response=response, body=None)
    transformed = llm.VertexAiLargeLanguageModel([])._transform_invoke_error(error)
    assert type(transformed) is invoke_error
    if invoke_error is not llm.InvokeAuthorizationError:
        # The original message (e.g. Marketplace terms not accepted) must reach the user.
        assert "not allowed to use this model" in str(transformed)


def test_plugin_bad_request_errors_stay_bad_requests():
    transformed = llm.VertexAiLargeLanguageModel([])._transform_invoke_error(InvokeBadRequestError("Unsupported document"))
    assert type(transformed) is InvokeBadRequestError


@pytest.mark.parametrize(
    ("model_name", "thinking_disabled"),
    [
        ("claude-sonnet-5", True),
        ("claude-sonnet-5@20260101", True),
        # Claude Sonnet 5.5 rejects disabled thinking, so the prefix must not match it.
        ("claude-sonnet-5-5", False),
        ("claude-opus-4-8", False),
        ("claude-sonnet-4-6", False),
    ],
)
def test_thinking_disabled_only_for_matching_models(model_name, thinking_disabled):
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [
        UserPromptMessage(content="Weather?"),
        AssistantPromptMessage(content="", tool_calls=[_tool_call("toolu_1", '{"city": "Tokyo"}')]),
        ToolPromptMessage(content="Sunny", tool_call_id="toolu_1", name="get_weather"),
    ]
    kwargs = model._build_claude_request_kwargs(model_name, prompt_messages, {"max_tokens": 10}, [TOOL])
    assert ("thinking" in kwargs) is thinking_disabled


def _tool_call(tool_call_id, arguments):
    return AssistantPromptMessage.ToolCall(
        id=tool_call_id,
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(name="get_weather", arguments=arguments),
    )


def test_assistant_text_and_tool_calls_with_malformed_arguments():
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [
        UserPromptMessage(content="Weather?"),
        AssistantPromptMessage(
            content="Let me check",
            tool_calls=[_tool_call("toolu_1", ""), _tool_call("toolu_2", '{"city": "To'), _tool_call("toolu_3", "[]")],
        ),
    ]
    kwargs = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})
    content = kwargs["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "Let me check"}
    assert [block["input"] for block in content[1:]] == [{}, {}, {}]


def test_tool_result_not_merged_into_user_content():
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [
        _user(_document("text/plain", b"notes")),
        AssistantPromptMessage(content="", tool_calls=[_tool_call("toolu_1", "{}")]),
        ToolPromptMessage(content="Sunny", tool_call_id="toolu_1", name="get_weather"),
    ]
    messages = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})["messages"]
    # The tool result must not be appended to the earlier user turn that holds text and a document.
    assert [block["type"] for block in messages[0]["content"]] == ["document", "text"]
    assert messages[2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "Sunny"}],
    }


def test_empty_user_turn_is_dropped():
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [UserPromptMessage(content="Hi"), UserPromptMessage(content=[TextPromptMessageContent(data="")])]
    messages = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})["messages"]
    assert messages == [{"role": "user", "content": "Hi"}]


def test_empty_assistant_turns_and_text_blocks_are_dropped():
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [
        UserPromptMessage(content="Hi"),
        AssistantPromptMessage(content=""),
        UserPromptMessage(content=[_document("text/plain", b"notes", "a.txt"), TextPromptMessageContent(data="")]),
    ]
    messages = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})["messages"]
    assert [m["role"] for m in messages] == ["user", "user"]
    assert [block["type"] for block in messages[1]["content"]] == ["document"]


def test_tool_message_list_content_and_tool_without_parameters():
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [
        UserPromptMessage(content="Time?"),
        AssistantPromptMessage(content="", tool_calls=[_tool_call("toolu_1", "{}")]),
        ToolPromptMessage(
            content=[TextPromptMessageContent(data="12:"), TextPromptMessageContent(data="00")],
            tool_call_id="toolu_1",
            name="get_time",
        ),
    ]
    tool = PromptMessageTool(name="get_time", description="Get the time", parameters={})
    kwargs = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10}, [tool])
    assert kwargs["messages"][2]["content"][0]["content"] == "12:00"
    assert kwargs["tools"][0]["input_schema"] == {"type": "object", "properties": {}}


def test_stop_sequences_passed_only_when_set():
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [UserPromptMessage(content="Hi")]
    assert model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10}, stop=["\n\n"])[
        "stop_sequences"
    ] == ["\n\n"]
    assert "stop_sequences" not in model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})


def test_service_account_token_used(monkeypatch):
    vertex, _ = _mock_client(monkeypatch, final_message=_message([TextBlock(type="text", text="hi")]))
    gcp_credentials = Mock(token="tok")
    monkeypatch.setattr(
        llm.service_account.Credentials, "from_service_account_info", Mock(return_value=gcp_credentials)
    )
    credentials = {**CREDENTIALS, "vertex_service_account_key": base64.b64encode(b'{"type": "service_account"}').decode()}
    model = llm.VertexAiLargeLanguageModel([])
    result = model._generate_anthropic(MODEL, credentials, [UserPromptMessage(content="Hi")], {"max_tokens": 10}, stream=False)
    gcp_credentials.refresh.assert_called_once()
    assert vertex.call_args.kwargs["access_token"] == "tok"
    # The credentials dict must not be shadowed by the Google credentials object.
    assert result.usage.prompt_tokens == 10


def test_tool_result_only_merges_into_tool_result_turn():
    model = llm.VertexAiLargeLanguageModel([])
    prompt_messages = [
        _user(_document("text/plain", b"notes")),
        ToolPromptMessage(content="Sunny", tool_call_id="toolu_1", name="get_weather"),
    ]
    messages = model._build_claude_request_kwargs(MODEL, prompt_messages, {"max_tokens": 10})["messages"]
    assert [[block["type"] for block in m["content"]] for m in messages] == [["document", "text"], ["tool_result"]]
