"""Tool-level tests for the MiniMax image generate/edit tools (no network)."""

from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from dify_plugin.entities.tool import ToolInvokeMessage

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


def _load_tool_module(file_name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_ROOT / "tools" / file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


generate = _load_tool_module("image-generate.py", "image_generate")
edit = _load_tool_module("image-edit.py", "image_edit")

ImageGenerateTool = generate.ImageGenerateTool
ImageEditTool = edit.ImageEditTool

CREDENTIALS = {"api_key": "test-key", "api_endpoint": "international"}


def _make(tool_cls):
    """Build a tool instance without the SDK runtime, the way the daemon would have it."""
    tool = tool_cls.__new__(tool_cls)
    tool.runtime = SimpleNamespace(credentials=CREDENTIALS)
    tool.response_type = ToolInvokeMessage
    return tool


def _texts(messages) -> list[str]:
    return [message.message.text for message in messages]


def _response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


def _ok_payload(*urls: str) -> dict:
    return {"base_resp": {"status_code": 0}, "data": [{"url": url} for url in urls]}


def test_generate_requires_a_prompt():
    tool = _make(ImageGenerateTool)
    assert _texts(tool._invoke({"prompt": "   "})) == ["Error: prompt is required"]


def test_generate_success_yields_images():
    tool = _make(ImageGenerateTool)
    with patch.object(requests, "post", return_value=_response(_ok_payload("https://a/1.png"))) as post:
        messages = list(tool._invoke({"prompt": "a cat", "n": 2, "aspect_ratio": "16:9", "area": "2K"}))

    assert _texts(messages) == ["https://a/1.png"]
    body = post.call_args.kwargs["json"]
    assert body["model"] == "MiniMax-H3-Image"
    assert body["n"] == 2
    assert body["aspect_ratio"] == "16:9"
    assert body["area"] == "2K"
    assert post.call_args.args[0] == "https://api.minimax.io/v1/images/generations"


def test_generate_api_failure_fails_the_invocation():
    tool = _make(ImageGenerateTool)
    payload = {"base_resp": {"status_code": 1004, "status_msg": "login fail"}}
    with patch.object(requests, "post", return_value=_response(payload)):
        with pytest.raises(ValueError, match="login fail"):
            list(tool._invoke({"prompt": "a cat"}))


def test_edit_requires_images():
    tool = _make(ImageEditTool)
    messages = list(tool._invoke({"prompt": "make it red"}))
    assert _texts(messages) == ["Error: images is required for image editing"]


def test_edit_rejects_more_than_16_images():
    tool = _make(ImageEditTool)
    image = SimpleNamespace(blob=b"x", mime_type="image/png", url=None)
    messages = list(tool._invoke({"prompt": "make it red", "images": [image] * 17}))
    assert _texts(messages) == ["Error: at most 16 reference images are supported"]


def test_edit_encodes_blobs_as_data_urls():
    tool = _make(ImageEditTool)
    blob = b"png-bytes"
    image = SimpleNamespace(blob=blob, mime_type="image/png", url=None)
    with patch.object(requests, "post", return_value=_response(_ok_payload("https://a/1.png"))) as post:
        messages = list(tool._invoke({"prompt": "make it red", "images": [image]}))

    assert _texts(messages) == ["https://a/1.png"]
    body = post.call_args.kwargs["json"]
    expected = "data:image/png;base64," + base64.b64encode(blob).decode("ascii")
    assert body["images"] == [{"image_url": expected}]
    assert post.call_args.args[0] == "https://api.minimax.io/v1/images/edits"


def test_edit_accepts_plain_urls():
    tool = _make(ImageEditTool)
    with patch.object(requests, "post", return_value=_response(_ok_payload("https://a/1.png"))) as post:
        list(tool._invoke({"prompt": "make it red", "images": ["https://example.com/a.png"]}))

    body = post.call_args.kwargs["json"]
    assert body["images"] == [{"image_url": "https://example.com/a.png"}]


def test_edit_rejects_unsupported_image_input():
    tool = _make(ImageEditTool)
    with pytest.raises(ValueError, match="unsupported image input"):
        list(tool._invoke({"prompt": "make it red", "images": [SimpleNamespace(blob=None, url=None)]}))
