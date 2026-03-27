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
            # First chunk with role
            yield "data: "
            yield json.dumps({
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1715806438,
                "model": request_body["model"],
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": None
                }]
            })
            yield "\n\n"
            
            # Content chunk
            yield "data: "
            yield json.dumps({
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1715806438,
                "model": request_body["model"],
                "choices": [{
                    "index": 0,
                    "delta": {"content": "Hello, world!"},
                    "finish_reason": None
                }]
            })
            yield "\n\n"
            
            # Final chunk
            yield "data: "
            yield json.dumps({
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1715806438,
                "model": request_body["model"],
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            })
            yield "\n\n"
            
            # End marker
            yield "data: [DONE]\n\n"

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


@app.post("/v1/moderations")
def openai_moderation_mock():
    return jsonify({
        "id": "modr-123",
        "model": "text-moderation-latest",
        "results": [
            {
                "flagged": False,
                "categories": {
                    "sexual": False,
                    "hate": False,
                    "harassment": False,
                    "self-harm": False,
                    "sexual/minors": False,
                    "hate/threatening": False,
                    "violence/graphic": False,
                    "self-harm/intent": False,
                    "self-harm/instructions": False,
                    "harassment/threatening": False,
                    "violence": False,
                },
                "category_scores": {
                    "sexual": 1.2e-4,
                    "hate": 2.1e-4,
                    "harassment": 3.4e-4,
                    "self-harm": 4.5e-4,
                    "sexual/minors": 5.6e-4,
                    "hate/threatening": 6.7e-4,
                    "violence/graphic": 7.8e-4,
                    "self-harm/intent": 8.9e-4,
                    "self-harm/instructions": 9.0e-4,
                    "harassment/threatening": 1.2e-3,
                    "violence": 2.3e-3,
                }
            }
        ]
    })


@app.post("/v1/audio/transcriptions")
def openai_audio_transcriptions_mock():
    return jsonify({"text": "Hello, world!"})


@app.post("/v1/embeddings")
def openai_embeddings_mock():
    request_body = request.get_json(force=True)
    input_text = request_body.get("input")
    if isinstance(input_text, str):
        input_text = [input_text]
    
    data = []
    import base64
    import numpy as np

    is_base64 = request_body.get("encoding_format") == "base64"

    for i, _ in enumerate(input_text):
        # Create a dummy embedding of size 1536 (common for openai models)
        embedding = [0.1] * 1536
        
        if is_base64:
             # Create a numpy array of float32
            embedding_array = np.array(embedding, dtype="float32")
            # Convert to bytes
            embedding_bytes = embedding_array.tobytes()
            # Encode to base64 string
            embedding_value = base64.b64encode(embedding_bytes).decode('utf-8')
        else:
            embedding_value = embedding

        data.append({
            "object": "embedding",
            "index": i,
            "embedding": embedding_value
        })

    return jsonify({
        "object": "list",
        "data": data,
        "model": request_body.get("model", "text-embedding-3-small"),
        "usage": {
            "prompt_tokens": 10,
            "total_tokens": 10
        }
    })


@app.post("/v1/audio/speech")
def openai_audio_speech_mock():
    # Return a dummy audio mp3 content
    dummy_audio_content = b"ID3\x03\x00\x00\x00\x00\nTIT2\x00\x00\x00\x05\x00\x00\x00Test"
    return Response(dummy_audio_content, mimetype="audio/mpeg")


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
