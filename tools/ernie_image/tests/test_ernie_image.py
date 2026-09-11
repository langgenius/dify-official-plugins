import base64
import os
import sys
from unittest.mock import MagicMock

import pytest
import yaml

PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from dify_plugin.errors.model import InvokeError  # noqa: E402
from dify_plugin.errors.tool import ToolProviderCredentialValidationError  # noqa: E402
from provider.ernie_image import ErnieImageProvider  # noqa: E402

from tools.ernie_image import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_SIZE,
    LEGACY_SIZES,
    OFFICIAL_SIZES,
    ErnieImageTool,
    _build_payload,
    _error_message,
    _fetch_image,
)


def test_build_payload_uses_compatible_defaults():
    assert _build_payload({"prompt": "  a cat  "}) == {
        "model": DEFAULT_MODEL,
        "prompt": "a cat",
        "n": 1,
        "size": DEFAULT_SIZE,
        "watermark": False,
    }


def test_build_payload_accepts_current_options_and_integer_seed():
    assert _build_payload(
        {
            "prompt": "海边日落",
            "model": "ernie-image",
            "size": "1376x768",
            "n": 2,
            "seed": "42",
            "watermark": True,
        }
    ) == {
        "model": "ernie-image",
        "prompt": "海边日落",
        "n": 2,
        "size": "1376x768",
        "seed": 42,
        "watermark": True,
    }


@pytest.mark.parametrize("size", sorted(LEGACY_SIZES))
def test_build_payload_keeps_legacy_sizes_compatible(size):
    assert _build_payload({"prompt": "a cat", "size": size})["size"] == size


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"prompt": ""}, "Prompt is required"),
        ({"prompt": "x" * 2049}, "2048"),
        ({"prompt": "x", "model": "unknown"}, "Unsupported model"),
        ({"prompt": "x", "size": "512x512"}, "Unsupported size"),
        ({"prompt": "x", "n": 0}, "between 1 and 4"),
        ({"prompt": "x", "n": 1.5}, "n must be an integer"),
        ({"prompt": "x", "seed": "1.5"}, "seed must be an integer"),
    ],
)
def test_build_payload_rejects_invalid_parameters(params, message):
    with pytest.raises(InvokeError, match=message):
        _build_payload(params)


def test_error_message_accepts_current_and_ai_studio_envelopes():
    assert _error_message({"errorMsg": "AI Studio error"}, "fallback") == "AI Studio error"
    assert _error_message({"message": "Current API error"}, "fallback") == "Current API error"
    assert _error_message({"error": {"message": "Nested error"}}, "fallback") == "Nested error"
    assert _error_message({}, "fallback") == "fallback"


def test_fetch_image_checks_status_and_uses_bounded_timeout(monkeypatch):
    response = MagicMock(content=b"image")
    get = MagicMock(return_value=response)
    monkeypatch.setattr("requests.get", get)

    assert _fetch_image("https://example.com/image.png") == b"image"
    get.assert_called_once_with("https://example.com/image.png", timeout=(10, 120))
    response.raise_for_status.assert_called_once_with()


def test_image_blob_accepts_base64_and_skips_invalid_content():
    assert ErnieImageTool._image_blob({"b64_json": base64.b64encode(b"image").decode()}) == b"image"
    assert ErnieImageTool._image_blob({"b64_json": "not-base64"}) is None


def test_invoke_emits_blob_and_current_response_metadata(monkeypatch):
    response = MagicMock(status_code=200, ok=True, content=b"{}")
    response.json.return_value = {
        "id": "image-request-id",
        "created": 1776827546,
        "trace_id": "ai-studio-trace",
        "data": [{"url": "https://example.com/image.png", "revised_prompt": "a cat"}],
    }
    post = MagicMock(return_value=response)
    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr("tools.ernie_image._fetch_image", lambda _url: b"image")
    monkeypatch.setattr(
        ErnieImageTool,
        "create_blob_message",
        lambda self, *, blob, meta: {"blob": blob, "meta": meta},
    )
    monkeypatch.setattr(
        ErnieImageTool,
        "create_json_message",
        lambda self, data: {"json": data},
    )

    tool = ErnieImageTool.from_credentials({"access_token": "  token  "})
    messages = list(tool._invoke({"prompt": "a cat"}))

    assert messages[0]["blob"] == b"image"
    assert messages[1]["json"]["id"] == "image-request-id"
    assert messages[1]["json"]["created"] == 1776827546
    assert messages[1]["json"]["trace_id"] == "ai-studio-trace"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer token"


def test_invoke_surfaces_current_error_message(monkeypatch):
    response = MagicMock(status_code=400, ok=False, content=b"{}", text="fallback")
    response.json.return_value = {
        "code": "invalid_argument",
        "message": "Unsupported size",
        "type": "invalid_request_error",
    }
    monkeypatch.setattr("requests.post", MagicMock(return_value=response))
    tool = ErnieImageTool.from_credentials({"access_token": "token"})

    with pytest.raises(InvokeError, match="Unsupported size"):
        list(tool._invoke({"prompt": "a cat"}))


def test_schema_lists_only_current_official_sizes():
    with open(os.path.join(PLUGIN_DIR, "tools", "ernie_image.yaml"), encoding="utf-8") as file:
        tool_schema = yaml.safe_load(file)
    parameters = {parameter["name"]: parameter for parameter in tool_schema["parameters"]}

    assert parameters["prompt"]["max_length"] == 2048
    assert parameters["model"]["default"] == DEFAULT_MODEL
    assert parameters["size"]["default"] == DEFAULT_SIZE
    assert {option["value"] for option in parameters["size"]["options"]} == OFFICIAL_SIZES


def test_manifest_version_is_bumped_without_changing_meta_version():
    with open(os.path.join(PLUGIN_DIR, "manifest.yaml"), encoding="utf-8") as file:
        manifest = yaml.safe_load(file)

    assert manifest["version"] == "0.0.4"
    assert manifest["meta"]["version"] == "0.0.1"


@pytest.mark.parametrize("token", [None, "", "   ", 123])
def test_provider_rejects_missing_or_invalid_token(token):
    provider = object.__new__(ErnieImageProvider)

    with pytest.raises(ToolProviderCredentialValidationError, match="Access token is required"):
        provider._validate_credentials({"access_token": token})
