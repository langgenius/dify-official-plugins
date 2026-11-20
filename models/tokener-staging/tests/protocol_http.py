import json
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessageTool,
    UserPromptMessage,
)

CREDENTIALS = {"api_key": "test-key", "endpoint_url": "https://ignored.invalid"}
USER = UserPromptMessage(content="hello")
TOOL = PromptMessageTool(
    name="lookup",
    description="Look up a record",
    parameters={"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1}}},
)
SCHEMA = {"type": "object", "properties": {"answer": {"type": "integer"}}}
PDF = DocumentPromptMessageContent(
    format=".pdf", mime_type="application/pdf", base64_data="JVBERi0xLjQK", filename="sample.pdf"
)
IMAGE = ImagePromptMessageContent(format=".png", mime_type="image/png", base64_data="iVBORw0KGgo=")


@pytest.fixture
def wire(monkeypatch):
    requests = []
    replies = deque()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.headers.get_content_type() == "application/json":
                body = json.loads(body)
            requests.append((self.path, self.headers, body))
            status, headers, payload = (
                replies.popleft() if replies else (500, {}, b"unexpected request")
            )
            if not isinstance(payload, bytes):
                payload = json.dumps(payload).encode()
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        monkeypatch.setattr("models._api.API_ORIGIN", origin)
        monkeypatch.setattr("models.llm._gemini_files.API_ORIGIN", origin)
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield origin, requests, replies
        finally:
            server.shutdown()
            thread.join(timeout=5)
    for _, headers, _ in requests:
        assert headers["Authorization"] in {"Bearer test-key", "Bearer other-key"}
        assert "x-goog-api-key" not in headers
    assert not replies


@pytest.fixture(scope="module")
def registry():
    return PluginRegistration(DifyPluginEnv())


@pytest.fixture
def llm(registry):
    return registry.get_model_instance("tokener", ModelType.LLM)


def invoke(
    llm,
    model,
    parameters=None,
    *,
    messages=None,
    stream=False,
    tools=None,
    stop=None,
    credentials=CREDENTIALS,
):
    return list(
        llm.invoke(
            model,
            credentials,
            [message.model_copy(deep=True) for message in (messages or [USER])],
            parameters or {},
            tools,
            stop,
            stream,
        )
    )


def sse(tag, **payload):
    return f"event: {tag}\r\ndata: {json.dumps(payload, ensure_ascii=False)}\r\n\r\n".encode()


def contents(chunks):
    return "".join(chunk.delta.message.get_text_content() for chunk in chunks)


def chat_result(content="ok", thinking=""):
    return {
        "choices": [
            {
                "message": {"content": content, "reasoning_content": thinking},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
    }
