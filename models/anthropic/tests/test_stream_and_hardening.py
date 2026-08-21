"""Regression tests for stream state machine, error mapping, and image fetching.

- The streaming handler used to emit the closing think tag a second time when a
  thinking block was followed directly by a tool_use block (current_block_type
  was left as "thinking" on input_json_delta and re-closed at MessageStopEvent).
- HTTP 529 OverloadedError fell through the APIError catch-all and was mapped
  to InvokeBadRequestError instead of InvokeServerUnavailableError.
- Image URL fetching had no timeout, no size cap, no scheme restriction and
  followed redirects.
"""

import base64
import io

import anthropic
import httpx
import pytest
from anthropic.types import (
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    InputJSONDelta,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
    ToolUseBlock,
    Usage,
)
from anthropic.types.raw_message_delta_event import Delta as MessageDelta
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import (
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel
from PIL import Image

OPEN_THINK = chr(60) + "think" + chr(62)
CLOSE_THINK = chr(60) + "/think" + chr(62)


def _message_start(input_tokens: int = 10) -> MessageStartEvent:
    message = Message(
        id="msg_1",
        content=[],
        model="claude-sonnet-4-5",
        role="assistant",
        type="message",
        usage=Usage(input_tokens=input_tokens, output_tokens=1),
    )
    return MessageStartEvent(type="message_start", message=message)


def _message_delta(stop_reason: str, output_tokens: int = 5) -> MessageDeltaEvent:
    return MessageDeltaEvent(
        type="message_delta",
        delta=MessageDelta(stop_reason=stop_reason),
        usage={"output_tokens": output_tokens},
    )


def _run_stream(events: list) -> list:
    return list(
        AnthropicLargeLanguageModel()._handle_chat_generate_stream_response(
            "claude-sonnet-4-5",
            {"anthropic_api_key": "test-key"},
            events,
            [UserPromptMessage(content="hi")],
        )
    )


def _emitted_text(chunks: list) -> str:
    return "".join(
        str(chunk.delta.message.content) for chunk in chunks if chunk.delta.message.content
    )


def test_thinking_then_tool_use_closes_think_tag_once() -> None:
    events = [
        _message_start(),
        ContentBlockStartEvent(
            type="content_block_start",
            index=0,
            content_block=ThinkingBlock(thinking="", signature="", type="thinking"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=0,
            delta=ThinkingDelta(type="thinking_delta", thinking="hmm"),
        ),
        ContentBlockStartEvent(
            type="content_block_start",
            index=1,
            content_block=ToolUseBlock(
                id="toolu_1", input={}, name="get_weather", type="tool_use"
            ),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=1,
            delta=InputJSONDelta(type="input_json_delta", partial_json='{"city": "Lisbon"}'),
        ),
        _message_delta("tool_use"),
        MessageStopEvent(type="message_stop"),
    ]

    chunks = _run_stream(events)
    text = _emitted_text(chunks)

    assert text.count(OPEN_THINK) == 1
    assert text.count(CLOSE_THINK) == 1
    assert "hmm" in text

    last = chunks[-1]
    assert last.delta.finish_reason == "tool_use"
    tool_calls = last.delta.message.tool_calls or []
    assert len(tool_calls) == 1
    assert tool_calls[0].function.name == "get_weather"
    assert tool_calls[0].function.arguments == '{"city": "Lisbon"}'


def test_thinking_then_text_closes_think_tag_once() -> None:
    events = [
        _message_start(),
        ContentBlockStartEvent(
            type="content_block_start",
            index=0,
            content_block=ThinkingBlock(thinking="", signature="", type="thinking"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=0,
            delta=ThinkingDelta(type="thinking_delta", thinking="hmm"),
        ),
        ContentBlockStartEvent(
            type="content_block_start",
            index=1,
            content_block=TextBlock(text="", type="text"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=1,
            delta=TextDelta(type="text_delta", text="hi there"),
        ),
        _message_delta("end_turn"),
        MessageStopEvent(type="message_stop"),
    ]

    chunks = _run_stream(events)
    text = _emitted_text(chunks)

    assert text.count(OPEN_THINK) == 1
    assert text.count(CLOSE_THINK) == 1
    assert "hi there" in text


def test_thinking_then_stop_closes_think_tag_once() -> None:
    events = [
        _message_start(),
        ContentBlockStartEvent(
            type="content_block_start",
            index=0,
            content_block=ThinkingBlock(thinking="", signature="", type="thinking"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=0,
            delta=ThinkingDelta(type="thinking_delta", thinking="hmm"),
        ),
        _message_delta("max_tokens"),
        MessageStopEvent(type="message_stop"),
    ]

    chunks = _run_stream(events)
    text = _emitted_text(chunks)

    assert text.count(OPEN_THINK) == 1
    assert text.count(CLOSE_THINK) == 1


def test_text_only_never_emits_think_tags() -> None:
    events = [
        _message_start(),
        ContentBlockStartEvent(
            type="content_block_start",
            index=0,
            content_block=TextBlock(text="", type="text"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=0,
            delta=TextDelta(type="text_delta", text="plain"),
        ),
        _message_delta("end_turn"),
        MessageStopEvent(type="message_stop"),
    ]

    chunks = _run_stream(events)
    text = _emitted_text(chunks)

    assert OPEN_THINK not in text
    assert CLOSE_THINK not in text
    assert "plain" in text


def test_thinking_then_parallel_tool_calls_closes_think_tag_once() -> None:
    events = [
        _message_start(),
        ContentBlockStartEvent(
            type="content_block_start",
            index=0,
            content_block=ThinkingBlock(thinking="", signature="", type="thinking"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=0,
            delta=ThinkingDelta(type="thinking_delta", thinking="hmm"),
        ),
        ContentBlockStartEvent(
            type="content_block_start",
            index=1,
            content_block=ToolUseBlock(
                id="toolu_1", input={}, name="get_weather", type="tool_use"
            ),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=1,
            delta=InputJSONDelta(type="input_json_delta", partial_json='{"city": "Lisbon"}'),
        ),
        ContentBlockStartEvent(
            type="content_block_start",
            index=2,
            content_block=ToolUseBlock(
                id="toolu_2", input={}, name="get_time", type="tool_use"
            ),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=2,
            delta=InputJSONDelta(type="input_json_delta", partial_json='{"zone": "UTC"}'),
        ),
        _message_delta("tool_use"),
        MessageStopEvent(type="message_stop"),
    ]

    chunks = _run_stream(events)
    text = _emitted_text(chunks)

    assert text.count(OPEN_THINK) == 1
    assert text.count(CLOSE_THINK) == 1

    tool_calls = chunks[-1].delta.message.tool_calls or []
    assert [(tc.function.name, tc.function.arguments) for tc in tool_calls] == [
        ("get_weather", '{"city": "Lisbon"}'),
        ("get_time", '{"zone": "UTC"}'),
    ]


def test_thinking_then_empty_tool_input_closes_think_tag_once() -> None:
    # A tool_use block that never emits an input_json_delta (empty input):
    # no block transition occurs, so the close tag must come at stream end — once.
    events = [
        _message_start(),
        ContentBlockStartEvent(
            type="content_block_start",
            index=0,
            content_block=ThinkingBlock(thinking="", signature="", type="thinking"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=0,
            delta=ThinkingDelta(type="thinking_delta", thinking="hmm"),
        ),
        ContentBlockStartEvent(
            type="content_block_start",
            index=1,
            content_block=ToolUseBlock(id="toolu_1", input={}, name="noop", type="tool_use"),
        ),
        _message_delta("tool_use"),
        MessageStopEvent(type="message_stop"),
    ]

    chunks = _run_stream(events)
    text = _emitted_text(chunks)

    assert text.count(OPEN_THINK) == 1
    assert text.count(CLOSE_THINK) == 1

    tool_calls = chunks[-1].delta.message.tool_calls or []
    assert len(tool_calls) == 1
    assert tool_calls[0].function.name == "noop"
    assert tool_calls[0].function.arguments == "{}"


def _status_error(cls: type, status_code: int):
    response = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    return cls(message="err", response=response, body=None)


def test_529_overloaded_maps_to_server_unavailable() -> None:
    llm = AnthropicLargeLanguageModel()
    transformed = llm._transform_invoke_error(_status_error(anthropic.OverloadedError, 529))
    assert isinstance(transformed, InvokeServerUnavailableError)


def test_500_and_429_mapping_unchanged() -> None:
    llm = AnthropicLargeLanguageModel()
    assert isinstance(
        llm._transform_invoke_error(_status_error(anthropic.InternalServerError, 500)),
        InvokeServerUnavailableError,
    )
    assert isinstance(
        llm._transform_invoke_error(_status_error(anthropic.RateLimitError, 429)),
        InvokeRateLimitError,
    )


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(buf, format="PNG")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "http://x/img"),
                response=httpx.Response(self.status_code),
            )

    def iter_content(self, chunk_size: int = 65536):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def close(self) -> None:
        pass


def test_image_fetch_uses_timeout_and_no_redirects(monkeypatch) -> None:
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(_png_bytes())

    monkeypatch.setattr(llm_module.requests, "get", fake_get)

    mime, b64 = AnthropicLargeLanguageModel()._process_image_data("http://x/img.png")

    assert mime == "image/png"
    assert base64.b64decode(b64) == _png_bytes()
    assert captured["kwargs"]["timeout"] == (5.0, 15.0)
    assert captured["kwargs"]["allow_redirects"] is False
    assert captured["kwargs"]["stream"] is True


def test_image_fetch_strips_surrounding_whitespace(monkeypatch) -> None:
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _FakeResponse(_png_bytes())

    monkeypatch.setattr(llm_module.requests, "get", fake_get)

    AnthropicLargeLanguageModel()._process_image_data("  http://x/img.png  ")

    assert captured["url"] == "http://x/img.png"


def test_image_fetch_rejects_non_http_schemes(monkeypatch) -> None:
    def fail_get(*args, **kwargs):
        raise AssertionError("requests.get must not be called for non-http(s) URLs")

    monkeypatch.setattr(llm_module.requests, "get", fail_get)

    with pytest.raises(ValueError, match="only http\\(s\\) URLs are allowed"):
        AnthropicLargeLanguageModel()._process_image_data("file:///etc/passwd")


def test_image_fetch_rejects_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_module.requests, "get", lambda url, **kw: _FakeResponse(b"", status_code=302)
    )

    with pytest.raises(ValueError, match="Redirect responses are not allowed"):
        AnthropicLargeLanguageModel()._process_image_data("http://x/img.png")


def test_image_fetch_rejects_redirect_even_with_valid_body(monkeypatch) -> None:
    # A 3xx with an image-like body must still be rejected, not consumed.
    monkeypatch.setattr(
        llm_module.requests,
        "get",
        lambda url, **kw: _FakeResponse(_png_bytes(), status_code=302),
    )

    with pytest.raises(ValueError, match="Redirect responses are not allowed"):
        AnthropicLargeLanguageModel()._process_image_data("http://x/img.png")


def test_image_fetch_rejects_oversized_content(monkeypatch) -> None:
    too_big = b"x" * (AnthropicLargeLanguageModel.MAX_IMAGE_FETCH_BYTES + 1)
    monkeypatch.setattr(llm_module.requests, "get", lambda url, **kw: _FakeResponse(too_big))

    with pytest.raises(ValueError, match="exceeds the 10 MB limit"):
        AnthropicLargeLanguageModel()._process_image_data("http://x/img.png")


def test_image_fetch_rejects_oversized_content_length_header(monkeypatch) -> None:
    # The declared Content-Length alone must trip the cap before downloading.
    response = _FakeResponse(b"")
    response.headers = {"Content-Length": str(AnthropicLargeLanguageModel.MAX_IMAGE_FETCH_BYTES + 1)}
    monkeypatch.setattr(llm_module.requests, "get", lambda url, **kw: response)

    with pytest.raises(ValueError, match="exceeds the 10 MB limit"):
        AnthropicLargeLanguageModel()._process_image_data("http://x/img.png")


def test_image_fetch_rejects_non_image_content(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_module.requests, "get", lambda url, **kw: _FakeResponse(b"not an image")
    )

    with pytest.raises(ValueError, match="Failed to fetch image"):
        AnthropicLargeLanguageModel()._process_image_data("http://x/img.png")


def test_data_uri_still_works() -> None:
    png = _png_bytes()
    data_uri = "data:image/png;base64," + base64.b64encode(png).decode("utf-8")

    mime, b64 = AnthropicLargeLanguageModel()._process_image_data(data_uri)

    assert mime == "image/png"
    assert base64.b64decode(b64) == png
