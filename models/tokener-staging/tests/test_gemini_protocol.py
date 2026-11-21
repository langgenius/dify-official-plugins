import base64
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeServerUnavailableError,
)
from gevent import sleep
from protocol_http import IMAGE, PDF, SCHEMA, TOOL, USER, contents, invoke, sse
from protocol_http import llm as llm
from protocol_http import registry as registry
from protocol_http import wire as wire

from models.llm import _gemini_files
from models.llm._gemini_native import DEFAULT_THOUGHT_SIGNATURE


def gemini_result(parts, finish="STOP", **extra):
    return {
        "candidates": [{"content": {"parts": parts}, "finishReason": finish, **extra}],
        "usageMetadata": {
            "promptTokenCount": 4,
            "candidatesTokenCount": 3,
            "thoughtsTokenCount": 2,
        },
    }


def test_gemini_interactions_keeps_native_tools_schema_and_stream_output(llm, wire):
    _, requests, replies = wire
    frames = sse("step.delta", delta={"type": "thought_summary", "content": {"text": "thinking"}})
    frames += sse(
        "interaction.complete",
        interaction={
            "status": "completed",
            "steps": [
                {"type": "model_output", "content": [{"type": "text", "text": '{"answer":4}'}]}
            ],
            "usage": {"total_input_tokens": 3, "total_output_tokens": 4, "total_thought_tokens": 2},
        },
    )
    replies.append((200, {}, frames))
    chunks = invoke(
        llm,
        "gemini-3-flash-preview",
        {
            "grounding": True,
            "url_context": True,
            "json_schema": SCHEMA,
            "max_output_tokens": 321,
            "media_resolution": "High",
            "include_thoughts": True,
            "thinking_level": "Low",
        },
        stream=True,
        messages=[UserPromptMessage(content=[IMAGE])],
    )
    path, _, body = requests[0]
    assert path == "/v1beta/interactions?alt=sse"
    assert body["tools"] == [{"type": "google_search"}, {"type": "url_context"}]
    assert body["response_format"]["schema"] == SCHEMA
    assert body["input"][0]["content"][0]["resolution"] == "high"
    assert body["generation_config"] == {
        "max_output_tokens": 321,
        "thinking_level": "low",
        "thinking_summaries": "auto",
    }
    assert contents(chunks) == '<think>\n\nthinking\n\n</think>{"answer":4}'
    assert chunks[-1].delta.usage.total_tokens == 9


def test_gemini_generate_uses_inline_pdf_and_replays_thought_signature(llm, wire):
    _, requests, replies = wire
    parts = [
        {"functionCall": {"name": "lookup", "args": {"limit": 1}}, "thoughtSignature": "signed"}
    ]
    replies.extend([(200, {}, gemini_result(parts)), (200, {}, gemini_result([{"text": "ok"}]))])
    params = {
        "use_inline_file": True,
        "media_resolution": "Medium",
        "thinking_level": "Low",
        "json_schema": SCHEMA,
        "tool_choice": {"type": "function", "function": {"name": "lookup"}},
    }
    model = "gemini-3-flash-preview"
    one = invoke(llm, model, params, tools=[TOOL], messages=[UserPromptMessage(content=[PDF])])[
        -1
    ].delta.message
    assert one.opaque_body == {"gemini_parts": parts}
    assert one.tool_calls[0].function.name == "lookup"
    invoke(
        llm,
        model,
        params,
        tools=[TOOL],
        messages=[
            USER,
            one,
            ToolPromptMessage(tool_call_id=one.tool_calls[0].id, content='{"found":true}'),
        ],
    )
    assert all(r[0] == f"/v1beta/models/{model}:generateContent" for r in requests)
    body = requests[0][2]
    assert body["contents"][0]["parts"][0]["inlineData"] == {
        "mimeType": "application/pdf",
        "data": PDF.base64_data,
    }
    assert body["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_MEDIUM"
    assert body["generationConfig"]["responseJsonSchema"] == SCHEMA
    assert body["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"] == TOOL.parameters
    assert body["toolConfig"] == {
        "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["lookup"]}
    }
    assert requests[1][2]["contents"][-2]["parts"] == parts
    assert requests[1][2]["contents"][-1]["parts"] == [
        {"functionResponse": {"name": "lookup", "response": {"response": '{"found":true}'}}}
    ]


@pytest.mark.parametrize("keep_opaque", [True, False])
def test_gemini_replays_parallel_same_name_tools_with_ids(llm, wire, keep_opaque):
    _, requests, replies = wire
    parts = [
        {"functionCall": {"id": "first", "name": "lookup", "args": {"id": 1}}},
        {"functionCall": {"id": "second", "name": "lookup", "args": {"id": 2}}},
    ]
    replies.extend([(200, {}, gemini_result(parts)), (200, {}, gemini_result([{"text": "ok"}]))])
    model = "gemini-3-flash-preview"
    message = invoke(llm, model, tools=[TOOL])[-1].delta.message
    assert [call.id for call in message.tool_calls] == ["first", "second"]
    if not keep_opaque:
        message = message.model_copy(update={"opaque_body": None})
    results = [
        ToolPromptMessage(tool_call_id=call.id, content='{"found":true}')
        for call in reversed(message.tool_calls)
    ]
    invoke(llm, model, tools=[TOOL], messages=[USER, message, *results])
    turns = requests[1][2]["contents"]
    assert turns[-2]["parts"] == [
        {**part, "thoughtSignature": DEFAULT_THOUGHT_SIGNATURE} for part in parts
    ]
    assert all("thoughtSignature" not in part for part in parts)
    assert turns[-1]["parts"] == [
        {
            "functionResponse": {
                "id": call_id,
                "name": "lookup",
                "response": {"response": '{"found":true}'},
            }
        }
        for call_id in ("second", "first")
    ]


@pytest.mark.parametrize("function_call", ["unexpected shape", {"id": []}])
def test_gemini_rejects_invalid_function_history_before_sending(llm, wire, function_call):
    _, requests, _ = wire
    history = AssistantPromptMessage(
        opaque_body={"gemini_parts": [{"functionCall": function_call}]},
    )
    with pytest.raises(InvokeBadRequestError, match="Invalid Gemini assistant history"):
        invoke(llm, "gemini-3-flash-preview", messages=[USER, history, USER])
    assert not requests


def test_gemini_resume_upload_cache_is_key_scoped(llm, wire):
    origin, requests, replies = wire
    upload = "/upload/v1beta/files"
    session = upload + "/366c2a2a-9e9a-419d-8ae0-846e9eb2baf7"
    file = origin + "/v1beta/files/tkf1" + "ab" * 32
    accepted = gemini_result([{"text": "ok"}])

    def upload_replies():
        return [
            (200, {"X-Goog-Upload-URL": origin + session}, {}),
            (200, {}, {"file": {"uri": file, "state": "ACTIVE"}}),
        ]

    replies.extend(
        [
            *upload_replies(),
            (200, {}, accepted),
            (200, {}, accepted),
            *upload_replies(),
            (200, {}, accepted),
        ]
    )
    model = "gemini-3-flash-preview"
    params = {"use_inline_file": False}
    messages = [UserPromptMessage(content=[PDF])]
    invoke(llm, model, params, messages=messages)
    invoke(llm, model, params, messages=messages)
    invoke(llm, model, params, messages=messages, credentials={"api_key": "other-key"})
    generate = f"/v1beta/models/{model}:generateContent"
    assert [r[0] for r in requests] == [
        upload,
        session,
        generate,
        generate,
        upload,
        session,
        generate,
    ]
    assert requests[0][1]["X-Goog-Upload-Command"] == "start"
    assert requests[0][2] == {"file": {"mime_type": "application/pdf", "size_bytes": 9}}
    assert requests[1][1]["X-Goog-Upload-Command"] == "upload, finalize"
    assert requests[1][2] == b"%PDF-1.4\n"
    assert requests[2][2]["contents"][0]["parts"] == [
        {"fileData": {"mimeType": "application/pdf", "fileUri": file}}
    ]


def test_gemini_rejects_cross_origin_upload_url_without_requesting_it(llm, wire):
    _, requests, replies = wire
    replies.append(
        (
            200,
            {
                "X-Goog-Upload-URL": "https://untrusted.invalid/upload/v1beta/files/366c2a2a-9e9a-419d-8ae0-846e9eb2baf7"
            },
            {},
        )
    )
    different = PDF.model_copy(update={"base64_data": "QW5vdGhlciBQREY="})
    with pytest.raises(InvokeServerUnavailableError, match="invalid Gemini upload URL"):
        invoke(llm, "gemini-3-flash-preview", messages=[UserPromptMessage(content=[different])])
    assert len(requests) == 1


def test_gemini_continuation_yields_images_and_sums_usage(llm, wire):
    _, requests, replies = wire
    replies.extend(
        [
            (200, {}, gemini_result([{"text": "wait"}], continuationToken="continue")),
            (
                200,
                {},
                gemini_result(
                    [{"inlineData": {"mimeType": "image/png", "data": IMAGE.base64_data}}]
                ),
            ),
        ]
    )
    chunks = invoke(llm, "gemini-3-pro-image-preview", {"resolution": "2K", "aspect_ratio": "1:1"})
    assert len(chunks) == 1
    msg = chunks[0].delta.message
    assert msg.content[-1].base64_data == IMAGE.base64_data
    assert requests[0][2]["generationConfig"]["imageConfig"] == {
        "aspectRatio": "1:1",
        "imageSize": "2K",
    }
    assert requests[1][2]["continuationToken"] == "continue"
    assert chunks[0].delta.usage.total_tokens == 18


@pytest.mark.parametrize("delay", [False, True])
def test_attachment_download_rejects_truncated_response_and_times_out(monkeypatch, delay):
    def read(_limit):
        if delay:
            sleep(1)
        return b"partial"

    response = MagicMock(status=200, length=100, read=read)
    response.__enter__.return_value = response
    transport = SimpleNamespace(request=Mock(), getresponse=lambda: response, close=Mock())
    monkeypatch.setattr(_gemini_files, "PublicHTTPSConnection", lambda *args, **kwargs: transport)
    monkeypatch.setattr(_gemini_files, "DOWNLOAD_SECONDS", 0.05)
    with pytest.raises(InvokeConnectionError, match="timed out" if delay else "ended early"):
        _gemini_files._download("https://example.invalid/file.pdf")
    transport.close.assert_called_once()
    response.__exit__.assert_called_once()


@pytest.mark.parametrize("kind", ["url", "base64", "history", "history-snake", "inline-pdf"])
def test_gemini_limits_inline_media_across_the_invocation(llm, wire, monkeypatch, kind):
    _, requests, replies = wire
    monkeypatch.setattr(_gemini_files, "MAX_BYTES", 8)
    data = base64.b64encode(b"12345").decode()
    image = IMAGE.model_copy(update={"base64_data": data})
    parameters = {}
    if kind == "url":
        image = IMAGE.model_copy(update={"base64_data": "", "url": "https://example.invalid/a"})
        response = MagicMock(status=200, length=5)
        response.__enter__.return_value = response
        response.read.return_value = b"12345"
        transport = SimpleNamespace(request=Mock(), getresponse=lambda: response, close=Mock())
        monkeypatch.setattr(_gemini_files, "PublicHTTPSConnection", lambda *args, **kw: transport)
    if kind == "inline-pdf":
        image = PDF.model_copy(update={"base64_data": data})
        parameters = {"use_inline_file": True}
    messages = [UserPromptMessage(content=[image]), UserPromptMessage(content=[image])]
    if kind in {"history", "history-snake"}:
        field = "inlineData" if kind == "history" else "inline_data"
        messages[0] = AssistantPromptMessage(
            opaque_body={"gemini_parts": [{field: {"mimeType": "image/png", "data": data}}]}
        )
    with pytest.raises(InvokeBadRequestError):
        invoke(llm, "gemini-3-flash-preview", parameters, messages=messages)
    assert not requests
    if kind == "url":
        assert response.read.call_count == 1
        assert transport.close.call_count == 2
    image = IMAGE.model_copy(update={"base64_data": base64.b64encode(b"1234").decode()})
    replies.append((200, {}, gemini_result([{"text": "ok"}])))
    invoke(
        llm,
        "gemini-3-flash-preview",
        messages=[UserPromptMessage(content=[image]), UserPromptMessage(content=[image])],
    )
    parts = requests[0][2]["contents"][0]["parts"]
    assert sum(len(base64.b64decode(part["inlineData"]["data"])) for part in parts) == 8


def test_attachment_connection_rejects_nonpublic_dns_before_opening_socket(monkeypatch):
    monkeypatch.setattr(
        _gemini_files.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
    )
    open_socket = Mock()
    monkeypatch.setattr(_gemini_files.socket, "socket", open_socket)
    transport = _gemini_files.PublicHTTPSConnection("example.invalid", timeout=1)
    with pytest.raises(InvokeBadRequestError, match="public HTTPS address"):
        transport.connect()
    open_socket.assert_not_called()


def test_attachment_connection_closes_tls_socket_when_handshake_is_interrupted(monkeypatch):
    monkeypatch.setattr(
        _gemini_files.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))
        ],
    )
    raw_socket = Mock()
    monkeypatch.setattr(_gemini_files.socket, "socket", Mock(return_value=raw_socket))
    tls_socket = Mock()
    tls_socket.do_handshake.side_effect = InvokeConnectionError("test handshake interruption")
    context = Mock(return_value=tls_socket)
    transport = _gemini_files.PublicHTTPSConnection(
        "example.invalid", timeout=1, context=SimpleNamespace(wrap_socket=context)
    )
    with pytest.raises(InvokeConnectionError, match="handshake interruption"):
        transport.connect()
    context.assert_called_once_with(
        raw_socket, server_hostname="example.invalid", do_handshake_on_connect=False
    )
    tls_socket.close.assert_called_once()
