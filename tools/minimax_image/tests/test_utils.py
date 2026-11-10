"""Unit tests for utils.emit_images and the provider credential validation.

No network: requests is mocked, and the MiniMax response shapes are the ones documented at
platform.minimax.io (a ``base_resp`` envelope whose ``status_code`` is 0 on success).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.errors.tool import ToolProviderCredentialValidationError  # noqa: E402

import utils  # noqa: E402
from provider.minimax_image import MiniMaxImageProvider  # noqa: E402

CREDENTIALS = {"api_key": "test-key", "api_endpoint": "international"}


class _FakeTool:
    """Stands in for the SDK Tool: records the messages emit_images produces."""

    def __init__(self) -> None:
        self.images: list[str] = []
        self.texts: list[str] = []

    def create_image_message(self, image_url: str, meta: dict | None = None):
        self.images.append(image_url)
        return ("image", image_url)

    def create_text_message(self, text: str):
        self.texts.append(text)
        return ("text", text)


def _response(*, status_code: int = 200, payload: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = text
    return response


def _ok_payload(*urls: str) -> dict:
    return {
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": [{"url": url} for url in urls],
    }


def _consume(generator) -> list:
    return list(generator)


def test_success_yields_every_image():
    tool = _FakeTool()
    payload = _ok_payload("https://a/1.png", "https://a/2.png")
    with patch.object(requests, "post", return_value=_response(payload=payload)) as post:
        messages = _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {"prompt": "a cat"}))

    assert [m[0] for m in messages] == ["image", "image"]
    assert tool.images == ["https://a/1.png", "https://a/2.png"]
    assert post.call_args.args[0] == "https://api.minimax.io/v1/images/generations"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"


def test_china_endpoint_is_used_when_selected():
    tool = _FakeTool()
    payload = _ok_payload("https://a/1.png")
    with patch.object(requests, "post", return_value=_response(payload=payload)) as post:
        _consume(utils.emit_images(tool, {"api_key": "k", "api_endpoint": "china"}, "/v1/images/generations", {}))

    assert post.call_args.args[0] == "https://api.minimaxi.com/v1/images/generations"
    assert tool.images == ["https://a/1.png"]


def test_transport_failure_raises_instead_of_returning_text():
    tool = _FakeTool()
    with patch.object(requests, "post", side_effect=requests.ConnectionError("connection reset")):
        with pytest.raises(ValueError, match="Failed to call MiniMax Image API"):
            _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {}))

    assert tool.texts == []


def test_unparseable_body_raises():
    tool = _FakeTool()
    response = _response(payload=None, text="<html>502</html>")
    response.json.side_effect = ValueError("no json")
    with patch.object(requests, "post", return_value=response):
        with pytest.raises(ValueError, match="Got Error Response"):
            _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {}))


def test_http_error_raises():
    tool = _FakeTool()
    with patch.object(requests, "post", return_value=_response(status_code=500, payload={}, text="boom")):
        with pytest.raises(ValueError, match="Got Error Response"):
            _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {}))


def test_rejected_key_raises_with_the_minimax_message():
    tool = _FakeTool()
    payload = {"base_resp": {"status_code": 1004, "status_msg": "login fail"}}
    with patch.object(requests, "post", return_value=_response(payload=payload)):
        with pytest.raises(ValueError, match="login fail"):
            _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {}))


def test_insufficient_balance_raises():
    tool = _FakeTool()
    payload = {"base_resp": {"status_code": 1008, "status_msg": "insufficient balance"}}
    with patch.object(requests, "post", return_value=_response(payload=payload)):
        with pytest.raises(ValueError, match="insufficient balance"):
            _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {}))


def test_empty_result_raises():
    tool = _FakeTool()
    with patch.object(requests, "post", return_value=_response(payload=_ok_payload())):
        with pytest.raises(ValueError, match="no image data"):
            _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {}))


def test_entries_without_a_url_are_skipped():
    tool = _FakeTool()
    payload = {
        "base_resp": {"status_code": 0},
        "data": [{"image_url": "https://a/1.png"}, {"url": "https://a/2.png"}],
    }
    with patch.object(requests, "post", return_value=_response(payload=payload)):
        messages = _consume(utils.emit_images(tool, CREDENTIALS, "/v1/images/generations", {}))

    assert len(messages) == 1
    assert tool.images == ["https://a/2.png"]


def test_empty_api_key_is_rejected_without_any_request():
    provider = MiniMaxImageProvider.__new__(MiniMaxImageProvider)
    with patch.object(requests, "get") as get:
        with pytest.raises(ToolProviderCredentialValidationError, match="required"):
            provider._validate_credentials({"api_key": "  "})

    get.assert_not_called()


def test_rejected_key_is_reported_as_credential_error():
    provider = MiniMaxImageProvider.__new__(MiniMaxImageProvider)
    payload = {"base_resp": {"status_code": 1004, "status_msg": "login fail"}}
    with patch.object(requests, "get", return_value=_response(payload=payload)) as get:
        with pytest.raises(ToolProviderCredentialValidationError, match="rejected the API key"):
            provider._validate_credentials(CREDENTIALS)

    assert get.call_args.args[0] == "https://api.minimax.io/v1/files/list"
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"


def test_valid_key_passes():
    provider = MiniMaxImageProvider.__new__(MiniMaxImageProvider)
    payload = {"base_resp": {"status_code": 0}, "files": []}
    with patch.object(requests, "get", return_value=_response(payload=payload)):
        provider._validate_credentials(CREDENTIALS)


def test_china_key_is_checked_against_the_china_endpoint():
    provider = MiniMaxImageProvider.__new__(MiniMaxImageProvider)
    payload = {"base_resp": {"status_code": 0}}
    with patch.object(requests, "get", return_value=_response(payload=payload)) as get:
        provider._validate_credentials({"api_key": "k", "api_endpoint": "china"})

    assert get.call_args.args[0] == "https://api.minimaxi.com/v1/files/list"


def test_unreachable_endpoint_is_reported_as_credential_error():
    provider = MiniMaxImageProvider.__new__(MiniMaxImageProvider)
    with patch.object(requests, "get", side_effect=requests.Timeout("timed out")):
        with pytest.raises(ToolProviderCredentialValidationError, match="Could not reach"):
            provider._validate_credentials(CREDENTIALS)
