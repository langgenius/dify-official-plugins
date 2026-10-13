"""Unit tests for the Bedrock Stability image generation tool."""

from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

_dify_plugin = sys.modules.get("dify_plugin") or type(sys)("dify_plugin")


class _FakeToolInvokeMessage:
    pass


class _FakeTool:
    def create_text_message(self, text: str):
        return ("text", text)

    def create_blob_message(self, blob: bytes, meta: dict | None = None):
        return ("blob", blob, meta or {})


_dify_plugin.Tool = _FakeTool  # type: ignore[attr-defined]
_dify_plugin_entities = sys.modules.get("dify_plugin.entities") or type(sys)(
    "dify_plugin.entities"
)
_dify_plugin_entities_tool = sys.modules.get("dify_plugin.entities.tool") or type(sys)(
    "dify_plugin.entities.tool"
)
_dify_plugin_entities_tool.ToolInvokeMessage = _FakeToolInvokeMessage
_dify_plugin.entities = _dify_plugin_entities  # type: ignore[attr-defined]
_dify_plugin.entities.tool = _dify_plugin_entities_tool  # type: ignore[attr-defined]
sys.modules.setdefault("dify_plugin", _dify_plugin)
sys.modules.setdefault("dify_plugin.entities", _dify_plugin_entities)
sys.modules.setdefault("dify_plugin.entities.tool", _dify_plugin_entities_tool)

import bedrock_image as bedrock_image_mod  # noqa: E402

BedrockImageTool = bedrock_image_mod.BedrockImageTool
MODEL_SD35 = bedrock_image_mod.MODEL_SD35
MODEL_CORE = bedrock_image_mod.MODEL_CORE
MODEL_ULTRA = bedrock_image_mod.MODEL_ULTRA

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
TINY_PNG_B64 = base64.b64encode(TINY_PNG).decode("utf-8")


def _consume(generator):
    return list(generator)


def _success_response(*, seed: int = 42, image_b64: str = TINY_PNG_B64) -> dict:
    body = {
        "seeds": [seed],
        "finish_reasons": [None],
        "images": [image_b64],
    }
    return {
        "body": io.BytesIO(json.dumps(body).encode("utf-8")),
        "ResponseMetadata": {"RequestId": "req-123", "HTTPStatusCode": 200},
    }


def _client_error(code: str, message: str, request_id: str = "req-err") -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"RequestId": request_id, "HTTPStatusCode": 400},
        },
        "InvokeModel",
    )


def _ref_image() -> SimpleNamespace:
    return SimpleNamespace(blob=TINY_PNG, mime_type="image/png")


@pytest.fixture
def tool() -> BedrockImageTool:
    return BedrockImageTool.__new__(BedrockImageTool)


def test_sd35_image_to_image_body_has_mode_and_no_aspect_ratio(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = _success_response()
    session = MagicMock()
    session.client.return_value = bedrock_client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a robot",
                    "model": MODEL_SD35,
                    "images": [_ref_image()],
                    "strength": 0.7,
                    "aspect_ratio": "16:9",
                }
            )
        )

    call_kwargs = bedrock_client.invoke_model.call_args.kwargs
    body = json.loads(call_kwargs["body"])
    assert call_kwargs["modelId"] == MODEL_SD35
    assert body["mode"] == "image-to-image"
    assert body["image"] == TINY_PNG_B64
    assert body["strength"] == 0.7
    assert "aspect_ratio" not in body
    assert any(m[0] == "blob" for m in messages)
    success = next(m for m in messages if m[0] == "text" and m[1].startswith("Image generated."))
    assert "model=stability.sd3-5-large-v1:0" in success[1]
    assert "request_id=req-123" in success[1]
    assert "strength=0.7" in success[1]


def test_ultra_image_to_image_body_has_no_mode(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = _success_response()
    session = MagicMock()
    session.client.return_value = bedrock_client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        _consume(
            tool._invoke(
                {
                    "prompt": "a robot",
                    "model": MODEL_ULTRA,
                    "images": [_ref_image()],
                    "strength": 0.35,
                }
            )
        )

    body = json.loads(bedrock_client.invoke_model.call_args.kwargs["body"])
    assert body["image"] == TINY_PNG_B64
    assert body["strength"] == 0.35
    assert "mode" not in body
    assert "aspect_ratio" not in body


def test_core_rejects_reference_image_without_invoke(tool: BedrockImageTool):
    with patch.object(bedrock_image_mod.boto3, "Session") as session_cls:
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a robot",
                    "model": MODEL_CORE,
                    "images": [_ref_image()],
                }
            )
        )

    session_cls.assert_not_called()
    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert MODEL_CORE in messages[0][1]
    assert "field=images" in messages[0][1]


def test_finish_reasons_without_images_returns_debug_text(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = {
        "body": io.BytesIO(
            json.dumps({"finish_reasons": ["Filter reason: prompt"]}).encode("utf-8")
        ),
        "ResponseMetadata": {"RequestId": "req-filter", "HTTPStatusCode": 200},
    }
    session = MagicMock()
    session.client.return_value = bedrock_client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        messages = _consume(tool._invoke({"prompt": "blocked prompt"}))

    assert len(messages) == 1
    text = messages[0][1]
    assert text.startswith("Bedrock returned no image.")
    assert "finish_reasons=Filter reason: prompt" in text
    assert "request_id=req-filter" in text
    assert "The safety filter rejected this request." in text
    assert not any(m[0] == "blob" for m in messages)


def test_inference_error_hint_is_not_safety_filter(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = {
        "body": io.BytesIO(
            json.dumps({"finish_reasons": ["Inference error"]}).encode("utf-8")
        ),
        "ResponseMetadata": {"RequestId": "req-inf", "HTTPStatusCode": 200},
    }
    session = MagicMock()
    session.client.return_value = bedrock_client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        messages = _consume(tool._invoke({"prompt": "a cat"}))

    text = messages[0][1]
    assert "finish_reasons=Inference error" in text
    assert "inference error" in text.lower()
    assert "safety filter" not in text.lower()


def test_invalid_s3_uri_rejected_before_invoke(tool: BedrockImageTool):
    with patch.object(bedrock_image_mod.boto3, "Session") as session_cls:
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "image_output_s3uri": "s3://",
                }
            )
        )

    session_cls.assert_not_called()
    assert "field=image_output_s3uri" in messages[0][1]


def test_oversized_reference_image_rejected(tool: BedrockImageTool):
    huge = SimpleNamespace(
        blob=b"x" * (bedrock_image_mod.MAX_INPUT_IMAGE_BYTES + 1),
        mime_type="image/png",
    )
    with patch.object(bedrock_image_mod.boto3, "Session") as session_cls:
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "model": MODEL_SD35,
                    "images": [huge],
                }
            )
        )

    session_cls.assert_not_called()
    assert "field=images.blob" in messages[0][1]
    assert "size=" in messages[0][1]


def test_client_error_includes_code_request_id_without_secret(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.side_effect = _client_error(
        "AccessDeniedException", "not authorized"
    )
    session = MagicMock()
    session.client.return_value = bedrock_client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "aws_access_key_id": "AKIATEST",
                    "aws_secret_access_key": "secret-value-should-not-leak",
                }
            )
        )

    text = messages[0][1]
    assert "error_code=AccessDeniedException" in text
    assert "request_id=req-err" in text
    assert "model=stability.sd3-5-large-v1:0" in text
    assert "region=us-west-2" in text
    assert "secret-value-should-not-leak" not in text
    assert "AKIATEST" not in text
    assert "hint=" in text


def test_only_access_key_does_not_create_client(tool: BedrockImageTool):
    with patch.object(bedrock_image_mod.boto3, "Session") as session_cls:
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "aws_access_key_id": "AKIATEST",
                }
            )
        )

    session_cls.assert_not_called()
    assert "field=aws_access_key_id/aws_secret_access_key" in messages[0][1]


def test_s3_upload_failure_still_returns_blob(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = _success_response()
    s3_client = MagicMock()
    s3_client.put_object.side_effect = ClientError(
        {
            "Error": {"Code": "AccessDenied", "Message": "denied"},
            "ResponseMetadata": {"RequestId": "s3-err"},
        },
        "PutObject",
    )

    def _client(service_name: str, **kwargs):
        if service_name == "bedrock-runtime":
            return bedrock_client
        if service_name == "s3":
            return s3_client
        raise AssertionError(f"unexpected service {service_name}")

    session = MagicMock()
    session.client.side_effect = _client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "image_output_s3uri": "s3://my-bucket/out",
                }
            )
        )

    kinds = [m[0] for m in messages]
    assert "blob" in kinds
    texts = [m[1] for m in messages if m[0] == "text"]
    assert any(t.startswith("Image was generated but S3 upload failed.") for t in texts)
    assert any(t.startswith("Image generated.") for t in texts)
    success = next(t for t in texts if t.startswith("Image generated."))
    assert "s3=upload-failed:s3://my-bucket/out" in success


def test_text_to_image_body_includes_aspect_ratio(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = _success_response(seed=99)
    session = MagicMock()
    session.client.return_value = bedrock_client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "model": MODEL_SD35,
                    "aspect_ratio": "16:9",
                    "seed": 0,
                }
            )
        )

    body = json.loads(bedrock_client.invoke_model.call_args.kwargs["body"])
    assert body["mode"] == "text-to-image"
    assert body["aspect_ratio"] == "16:9"
    assert "image" not in body
    success = next(m[1] for m in messages if m[0] == "text")
    assert "seed=99" in success
    assert "strength=omitted" in success


def test_core_rejects_webp_output(tool: BedrockImageTool):
    with patch.object(bedrock_image_mod.boto3, "Session") as session_cls:
        messages = _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "model": MODEL_CORE,
                    "output_format": "webp",
                }
            )
        )

    session_cls.assert_not_called()
    assert "field=output_format" in messages[0][1]
    assert "webp" in messages[0][1]


def test_explicit_credentials_passed_to_client(tool: BedrockImageTool):
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = _success_response()
    session = MagicMock()
    session.client.return_value = bedrock_client

    with patch.object(bedrock_image_mod.boto3, "Session", return_value=session):
        _consume(
            tool._invoke(
                {
                    "prompt": "a cat",
                    "aws_region": "us-west-2",
                    "aws_access_key_id": "AKIATEST",
                    "aws_secret_access_key": "SECRET",
                    "aws_session_token": "TOKEN",
                }
            )
        )

    args, kwargs = session.client.call_args
    assert args[0] == "bedrock-runtime"
    assert kwargs["region_name"] == "us-west-2"
    assert kwargs["aws_access_key_id"] == "AKIATEST"
    assert kwargs["aws_secret_access_key"] == "SECRET"
    assert kwargs["aws_session_token"] == "TOKEN"
