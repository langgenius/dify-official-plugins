import json
import subprocess
import sys
import time
import flask.cli
from flask import Flask, Response, jsonify, request

OPENAI_MOCK_SERVER_PORT = 12345

flask.cli.show_server_banner = lambda *args: None
app = Flask(__name__)


@app.post("/v1/chat/completions")
def openai_server_mock():
    request_body = request.get_json(force=True)
    if request_body.get("stream"):

        def stream_response():
            yield "data: "
            yield json.dumps({"choices": [{"message": {"content": "Hello, world!"}}]})
            yield "\n\n"

        return Response(stream_response(), mimetype="text/event-stream")
    else:
        return jsonify(
            {
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "created": 1715806438,
                "model": request_body["model"],
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hello, world!"},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            }
        )


class OpenAIMockServer:
    def __init__(self):
        # create subprocess
        # get self python path
        self.python_path = sys.executable
        self.process = subprocess.Popen(
            [
                self.python_path,
                "-m",
                "flask",
                "--app",
                "tests.models.__mockserver.openai:app",
                "run",
                "--port",
                str(OPENAI_MOCK_SERVER_PORT),
            ]
        )
        # wait for server to start
        time.sleep(1)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.process.terminate()
