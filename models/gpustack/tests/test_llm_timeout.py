"""Verify model-scoped timeouts at the real HTTP request boundary."""

# isort: off
from dify_plugin.entities.model.message import UserPromptMessage, PromptMessageTool
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError
from models.llm.llm import GPUStackLanguageModel

import json
import os
import unittest
from unittest.mock import Mock, patch

# isort: on


def credentials(**kwargs):
    return {
        "endpoint_url": "http://gpustack.test/v1",
        "api_key": "test-key",
        "mode": "chat",
        "context_size": "8192",
        **kwargs,
    }


def response():
    value = Mock()
    value.status_code = 200
    value.encoding = "utf-8"
    value.json.return_value = {
        "object": "chat.completion",
        "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    return value


class TimeoutTests(unittest.TestCase):
    def setUp(self):
        self.model = GPUStackLanguageModel(model_schemas=[])

    @patch("requests.post")
    def test_validation_failure_retries_keep_model_timeout(self, post):
        for reason in ["integer_below_min_value", "thinking budget_tokens is required"]:
            with self.subTest(reason=reason):
                failed = response()
                failed.status_code = 400
                failed.text = reason
                post.reset_mock()
                post.side_effect = [failed, response()]
                self.model.validate_credentials("test", credentials(request_timeout="720"))
                self.assertEqual(post.call_count, 2)
                self.assertEqual(
                    [c.kwargs["timeout"] for c in post.call_args_list], [(10, 720), (10, 720)]
                )

    @patch("requests.post")
    def test_invoke_preserves_json_schema_tools_and_parses_response(self, post):
        post.return_value = response()
        schema = {"name": "answer", "schema": {"type": "object", "properties": {}}}
        tool = PromptMessageTool(
            name="lookup",
            description="Look up a value",
            parameters={"type": "object", "properties": {}},
        )
        result = self.model._invoke(
            "test",
            credentials(request_timeout="900", function_calling_type="tool_call"),
            [UserPromptMessage(content="hello")],
            {"response_format": "json_schema", "json_schema": json.dumps(schema)},
            tools=[tool],
            stream=False,
        )
        self.assertEqual(result.message.content, "OK")
        body = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(body["response_format"], {"type": "json_schema", "json_schema": schema})
        self.assertEqual(body["tools"][0]["function"]["name"], "lookup")
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 900))

    @patch("requests.post")
    def test_invoke_stream_preserves_content_and_usage(self, post):
        reply = response()
        reply.iter_lines.return_value = iter(
            [
                "data: "
                + json.dumps(
                    {"choices": [{"index": 0, "delta": {"content": "OK"}, "finish_reason": None}]}
                ),
                "data: "
                + json.dumps(
                    {
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                ),
                "data: [DONE]",
            ]
        )
        post.return_value = reply
        chunks = list(
            self.model._invoke(
                "test",
                credentials(request_timeout="800"),
                [UserPromptMessage(content="hello")],
                {},
                stream=True,
            )
        )
        self.assertEqual("".join(c.delta.message.content or "" for c in chunks), "OK")
        self.assertEqual(chunks[-1].delta.usage.total_tokens, 2)
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 800))

    @patch("requests.post")
    def test_model_timeout_reaches_streaming_and_nonstreaming_http(self, post):
        post.return_value = response()
        for stream in [False, True]:
            with self.subTest(stream=stream), patch.object(
                self.model, "_handle_generate_response", return_value="ok"
            ), patch.object(self.model, "_handle_generate_stream_response", return_value=iter([])):
                self.model._generate(
                    "test",
                    credentials(request_timeout="900"),
                    [UserPromptMessage(content="hello")],
                    {},
                    stream=stream,
                )
                self.assertEqual(post.call_args.kwargs["timeout"], (10, 900))
                self.assertEqual(post.call_args.kwargs["stream"], stream)
                self.assertNotIn("request_timeout", json.loads(post.call_args.kwargs["data"]))

    @patch("requests.post")
    def test_models_keep_independent_timeout_settings(self, post):
        post.return_value = response()
        with patch.object(self.model, "_handle_generate_response", return_value="ok"):
            for seconds in [900, 45, 900]:
                self.model._generate(
                    "test",
                    credentials(request_timeout=str(seconds)),
                    [UserPromptMessage(content="hello")],
                    {},
                    stream=False,
                )
            self.assertEqual(
                [c.kwargs["timeout"] for c in post.call_args_list], [(10, 900), (10, 45), (10, 900)]
            )

    @patch("requests.post")
    def test_invalid_timeout_is_rejected_before_http(self, post):
        for value in ["abc", "0", "-1", "nan", "inf", True]:
            with self.subTest(value=value), self.assertRaises(InvokeBadRequestError):
                self.model._generate(
                    "test",
                    credentials(request_timeout=value),
                    [UserPromptMessage(content="hello")],
                    {},
                    stream=False,
                )
        post.assert_not_called()

    @patch("requests.post")
    def test_credential_validation_and_retry_use_configured_timeout(self, post):
        post.return_value = response()
        for stream in ["not_use", "use"]:
            for token in ["max_tokens", "max_completion_tokens"]:
                with self.subTest(stream=stream, token=token):
                    self.model.validate_credentials(
                        "test",
                        credentials(
                            request_timeout="900", stream_mode_auth=stream, token_param_name=token
                        ),
                    )
                    self.assertEqual(post.call_args.kwargs["timeout"], (10, 900))

    @patch("requests.post")
    def test_invalid_timeout_during_validation_has_validation_error(self, post):
        with self.assertRaises(CredentialsValidateFailedError):
            self.model.validate_credentials("test", credentials(request_timeout="-3"))
        post.assert_not_called()

    @patch("requests.post")
    def test_empty_timeout_uses_environment_default(self, post):
        post.return_value = response()
        with patch.dict(os.environ, {"MAX_REQUEST_TIMEOUT": "420"}), patch.object(
            self.model, "_handle_generate_response", return_value="ok"
        ):
            for value in [None, "", "   "]:
                self.model._generate(
                    "test",
                    credentials(request_timeout=value),
                    [UserPromptMessage(content="hello")],
                    {},
                    stream=False,
                )
                self.assertEqual(post.call_args.kwargs["timeout"], (10, 420))

    def test_real_http_read_timeout_is_enforced(self):
        import subprocess
        import sys

        import requests

        # Keep the server independent of the SDK's gevent monkey patches.
        script = """
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        time.sleep(0.3)
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(('127.0.0.1', 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()
"""
        server = subprocess.Popen(
            [sys.executable, "-u", "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            port = int(server.stdout.readline())
            with (
                patch.dict(os.environ, {"NO_PROXY": "127.0.0.1"}),
                self.assertRaises(requests.exceptions.ReadTimeout),
            ):
                self.model._generate(
                    "test",
                    credentials(endpoint_url=f"http://127.0.0.1:{port}/v1", request_timeout="0.05"),
                    [UserPromptMessage(content="hello")],
                    {},
                    stream=False,
                )
        finally:
            server.terminate()
            server.wait(timeout=5)
            server.stdout.close()


if __name__ == "__main__":
    unittest.main()
