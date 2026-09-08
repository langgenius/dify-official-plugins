"""
Hygiene regressions: request/response log levels, the removed pdfs beta
header, and the stream handler after the dead redacted-thinking delta
branches were removed.
"""

import base64
import logging

from anthropic.types import (
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    RedactedThinkingBlock,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
    Usage,
)
from anthropic.types.raw_message_delta_event import Delta as MessageDelta
from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)
from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel

# ---------------------------------------------------------------------------
# Fake client (same pattern as test_opus5_parameters.py)
# ---------------------------------------------------------------------------


class _Messages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return object()


class _Anthropic:
    instances: list["_Anthropic"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.messages = _Messages()
        self.instances.append(self)


def _capture_payload(
    monkeypatch,
    prompt_messages: list,
    model: str = "claude-opus-5",
) -> dict:
    _Anthropic.instances = []
    monkeypatch.setattr(llm_module, "Anthropic", _Anthropic)

    # stream=True: _chat_generate returns the (unconsumed) generator, so the
    # fake response object is never dereferenced.
    AnthropicLargeLanguageModel()._chat_generate(
        model=model,
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=prompt_messages,
        model_parameters={"max_tokens": 1024},
        stream=True,
    )

    return _Anthropic.instances[0].messages.calls[0]


# ---------------------------------------------------------------------------
# PDF beta header removal
# ---------------------------------------------------------------------------


_PDF_B64 = base64.b64encode(b"%PDF-1.4 fake").decode()


def _pdf_message() -> UserPromptMessage:
    # base64_data is the SDK field (data is a computed data-URI property).
    return UserPromptMessage(
        content=[
            DocumentPromptMessageContent(
                base64_data=_PDF_B64, mime_type="application/pdf", format="pdf"
            ),
            TextPromptMessageContent(data="Summarize"),
        ]
    )


def test_pdf_document_does_not_send_beta_header(monkeypatch) -> None:
    payload = _capture_payload(monkeypatch, [_pdf_message()])

    # The document block itself still goes through (PDF support is GA).
    messages = payload["messages"]
    document_blocks = [
        item
        for msg in messages
        for item in (msg["content"] if isinstance(msg["content"], list) else [])
        if item.get("type") == "document"
    ]
    assert len(document_blocks) == 1
    assert document_blocks[0]["source"]["media_type"] == "application/pdf"
    assert document_blocks[0]["source"]["data"] == _PDF_B64

    # The obsolete `pdfs-2024-09-25` beta header must not be sent.
    headers = payload.get("extra_headers") or {}
    assert "anthropic-beta" not in headers


def test_pdf_and_task_budget_only_send_task_budget_header(monkeypatch) -> None:
    _Anthropic.instances = []
    monkeypatch.setattr(llm_module, "Anthropic", _Anthropic)

    AnthropicLargeLanguageModel()._chat_generate(
        model="claude-opus-5",
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=[_pdf_message()],
        model_parameters={"max_tokens": 1024, "thinking": True, "task_budget": 64000},
        stream=True,
    )

    payload = _Anthropic.instances[0].messages.calls[0]
    # Only the task-budget beta remains — no comma-joined pdfs header.
    assert payload["extra_headers"] == {"anthropic-beta": "task-budgets-2026-03-13"}


# ---------------------------------------------------------------------------
# Log levels: full request/response dumps must not log at INFO
# ---------------------------------------------------------------------------


def test_request_logging_is_debug_not_info(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    _capture_payload(monkeypatch, [UserPromptMessage(content="Hello")])

    request_records = [r for r in caplog.records if "Anthropic API Request" in r.getMessage()]
    # The request is still logged ...
    assert request_records, "expected the Anthropic API request to be logged"
    # ... but at DEBUG, never at INFO (full payloads contain user content).
    assert all(r.levelno == logging.DEBUG for r in request_records)


def test_no_verbose_api_logging_at_info_or_above(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    _capture_payload(monkeypatch, [UserPromptMessage(content="Hello")])

    verbose_markers = (
        "Anthropic API Request",
        "Anthropic API Tools",
        "Blocks:",
    )
    offenders = [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.INFO and any(m in r.getMessage() for m in verbose_markers)
    ]
    assert offenders == []


# ---------------------------------------------------------------------------
# Stream handler after removing the dead redacted_thinking delta branches:
# a real redacted_thinking content_block_start must still be tolerated.
# ---------------------------------------------------------------------------


def _message_start(input_tokens: int = 5) -> MessageStartEvent:
    message = Message(
        id="msg_1",
        content=[],
        model="claude-opus-5",
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


def _run_stream(events) -> list:
    generator = AnthropicLargeLanguageModel()._handle_chat_generate_stream_response(
        model="claude-opus-5",
        credentials={"anthropic_api_key": "test-key"},
        response=iter(events),
        prompt_messages=[UserPromptMessage(content="Hello")],
    )
    return list(generator)


def _emitted_text(chunks) -> str:
    parts = []
    for chunk in chunks:
        content = chunk.delta.message.content
        if isinstance(content, str):
            parts.append(content)
    return "".join(parts)


OPEN_THINK = chr(60) + "think" + chr(62)
CLOSE_THINK = chr(60) + "/think" + chr(62)


def test_stream_redacted_thinking_block_start_between_blocks() -> None:
    # Real API shape: a redacted_thinking block arrives as a
    # content_block_start with NO deltas. The handler must skip it cleanly,
    # still close the thinking tag exactly once, and deliver the text.
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
            content_block=RedactedThinkingBlock(
                data="EUxvcmUgZmFjaw==", type="redacted_thinking"
            ),
        ),
        ContentBlockStartEvent(
            type="content_block_start",
            index=2,
            content_block=TextBlock(text="", type="text"),
        ),
        ContentBlockDeltaEvent(
            type="content_block_delta",
            index=2,
            delta=TextDelta(type="text_delta", text="hello"),
        ),
        _message_delta("end_turn"),
        MessageStopEvent(type="message_stop"),
    ]

    chunks = _run_stream(events)
    text = _emitted_text(chunks)

    assert text.count(OPEN_THINK) == 1
    assert text.count(CLOSE_THINK) == 1
    assert "hello" in text


# ---------------------------------------------------------------------------
# DEBUG payload logs must not pay serialization cost at the default INFO
# level: f-string arguments (json.dumps / model_dump_json) are evaluated
# before logging.debug() filters the record out.
# ---------------------------------------------------------------------------


def _spy_stream_serialization(monkeypatch) -> dict:
    calls = {"n": 0}
    for cls in (
        MessageStartEvent,
        ContentBlockStartEvent,
        ContentBlockDeltaEvent,
        MessageDeltaEvent,
        MessageStopEvent,
    ):
        origin = cls.model_dump_json

        def make_spy(origin):
            def spy(self, *args, **kwargs):
                calls["n"] += 1
                return origin(self, *args, **kwargs)

            return spy

        monkeypatch.setattr(cls, "model_dump_json", make_spy(origin))
    return calls


def test_stream_chunks_not_serialized_when_debug_disabled(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO)
    calls = _spy_stream_serialization(monkeypatch)
    events = [_message_start(), _message_delta("end_turn"), MessageStopEvent(type="message_stop")]

    _run_stream(events)

    assert calls["n"] == 0, "stream chunks serialized although DEBUG is disabled"
    assert not [
        r for r in caplog.records if "Anthropic API Stream Response Chunk" in r.getMessage()
    ]


def test_stream_chunks_serialized_when_debug_enabled(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    calls = _spy_stream_serialization(monkeypatch)
    events = [_message_start(), _message_delta("end_turn"), MessageStopEvent(type="message_stop")]

    _run_stream(events)

    assert calls["n"] == len(events), "DEBUG log must serialize every streamed chunk"
    assert [
        r for r in caplog.records if "Anthropic API Stream Response Chunk" in r.getMessage()
    ]


def test_request_payload_not_serialized_when_debug_disabled(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO)
    calls = {"n": 0}
    real_dumps = llm_module.json.dumps

    def spy(*args, **kwargs):
        # Only the payload log lines use indent=2; the non-logging uses
        # (tool schema, tool arguments) do not.
        if kwargs.get("indent") == 2 or (len(args) > 1 and args[1] == 2):
            calls["n"] += 1
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(llm_module.json, "dumps", spy)
    _capture_payload(monkeypatch, [UserPromptMessage(content="Hello")])

    assert calls["n"] == 0, "request payload serialized although DEBUG is disabled"


def test_request_payload_serialized_when_debug_enabled(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    calls = {"n": 0}
    real_dumps = llm_module.json.dumps

    def spy(*args, **kwargs):
        if kwargs.get("indent") == 2 or (len(args) > 1 and args[1] == 2):
            calls["n"] += 1
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(llm_module.json, "dumps", spy)
    _capture_payload(monkeypatch, [UserPromptMessage(content="Hello")])

    assert calls["n"] == 1, "DEBUG log must serialize the request payload once"
