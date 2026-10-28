import base64
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeError

from models.llm.documents import REQUEST_BODY_LIMIT
from models.llm.llm import TokenerLargeLanguageModel


def model():
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path("models/llm/qwen-long.yaml").read_text())
    )
    return TokenerLargeLanguageModel(model_schemas=[schema])


def messages(extension="pdf", question="Read the document.", **fields):
    return [
        UserPromptMessage(
            content=[
                TextPromptMessageContent(data=question),
                DocumentPromptMessageContent(
                    format=extension,
                    mime_type="application/octet-stream",
                    **(
                        fields or {"base64_data": base64.b64encode(b"document-only value").decode()}
                    ),
                ),
            ]
        )
    ]


def response(*args, **kwargs):
    value = requests.Response()
    value.status_code = 200
    value._content = json.dumps(
        {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1234, "completion_tokens": 17},
        }
    ).encode()
    return value


def error_response(status, body, content_type="application/json"):
    value = requests.Response()
    value.status_code = status
    value.headers["Content-Type"] = content_type
    value._content = body.encode()
    close = Mock(wraps=value.close)
    value.close = close
    return value, close


@pytest.mark.parametrize(
    ("status", "error_body", "expected"),
    [
        (
            429,
            {"error": {"message": "Insufficient balance. Add credits to continue."}},
            "Insufficient balance",
        ),
        (429, {"error": {"message": "Rate limit exceeded. Retry later."}}, "Rate limit exceeded"),
    ],
)
def test_http_errors_preserve_tokener_message_and_status(status, error_body, expected):
    failed, close = error_response(status, json.dumps(error_body))
    with patch("requests.post", return_value=failed):
        with pytest.raises(InvokeError) as error:
            list(
                model().invoke(
                    "qwen-long", {"api_key": "fake-test-key"}, messages(), {}, stream=False
                )
            )
    assert f"HTTP {status}" in str(error.value)
    assert expected in str(error.value)
    close.assert_called_once()


@pytest.mark.parametrize("field", ["message", "detail"])
def test_http_errors_accept_top_level_string_message_fields(field):
    failed, close = error_response(400, json.dumps({field: "The requested model is unavailable."}))
    with patch("requests.post", return_value=failed):
        with pytest.raises(InvokeError, match="The requested model is unavailable"):
            list(
                model().invoke(
                    "qwen-long", {"api_key": "fake-test-key"}, messages(), {}, stream=False
                )
            )
    close.assert_called_once()


def test_http_error_redacts_credential_values_bearer_and_secret_key_patterns():
    values = [
        "fake-test-api-key",
        "fake-service-secret",
        "fake-header-token",
        "fake-bearer-value",
        "sk-very-long-sensitive-key-1234",
    ]
    failed, close = error_response(
        401,
        json.dumps(
            {
                "error": {
                    "message": "Invalid fake-test-api-key, fake-service-secret, "
                    "fake-header-token, Bearer fake-bearer-value, and "
                    "sk-very-long-sensitive-key-1234"
                }
            }
        ),
    )
    credentials = {
        "api_key": values[0],
        "service_token": values[1],
        "extra_headers": {"X-Auth-Token": values[2]},
    }
    with patch("requests.post", return_value=failed):
        with pytest.raises(InvokeError) as error:
            list(model().invoke("qwen-long", credentials, messages(), {}, stream=False))
    for secret in values:
        assert secret not in str(error.value)
    assert "[REDACTED]" in str(error.value)
    close.assert_called_once()


def test_http_error_with_non_json_body_uses_generic_failure():
    failed, close = error_response(429, "<html>private proxy response</html>", "text/html")
    with patch("requests.post", return_value=failed):
        with pytest.raises(InvokeError) as error:
            list(
                model().invoke(
                    "qwen-long", {"api_key": "fake-test-key"}, messages(), {}, stream=False
                )
            )
    assert "The document request failed with HTTP 429." in str(error.value)
    assert "private proxy response" not in str(error.value)
    close.assert_called_once()


@pytest.mark.parametrize(
    "extension",
    [
        "txt",
        "docx",
        "pdf",
        "xlsx",
        "epub",
        "mobi",
        "md",
        "csv",
        "json",
        "bmp",
        "png",
        "jpg",
        "jpeg",
        "gif",
    ],
)
def test_supported_document_formats_keep_the_original_bytes(extension):
    with patch("requests.post", side_effect=response) as post:
        list(
            model().invoke(
                "qwen-long", {"api_key": "fake-test-key"}, messages(extension), {}, stream=False
            )
        )
    file = json.loads(post.call_args.kwargs["data"])["messages"][0]["content"][1]["file"]
    assert file["filename"].endswith("." + extension)
    assert base64.b64decode(file["file_data"].split(",", 1)[1]) == b"document-only value"


def test_image_prompt_uses_native_file_extraction_instead_of_vision_content():
    image = ImagePromptMessageContent(
        format="png",
        mime_type="image/png",
        base64_data=base64.b64encode(b"original image bytes").decode(),
    )
    with patch("requests.post", side_effect=response) as post:
        list(
            model().invoke(
                "qwen-long",
                {"api_key": "fake-test-key"},
                [
                    UserPromptMessage(
                        content=[TextPromptMessageContent(data="Read the image text."), image]
                    )
                ],
                {},
                stream=False,
            )
        )
    blocks = json.loads(post.call_args.kwargs["data"])["messages"][0]["content"]
    assert blocks[1]["type"] == "file"
    assert blocks[1]["file"]["filename"].endswith(".png")
    assert (
        base64.b64decode(blocks[1]["file"]["file_data"].split(",", 1)[1]) == b"original image bytes"
    )


@pytest.mark.parametrize("extension", ["doc", "pptx", "exe"])
def test_unsupported_documents_fail_before_network_access(extension):
    with patch("requests.post") as post, patch("requests.get") as get:
        with pytest.raises(InvokeBadRequestError):
            list(
                model().invoke(
                    "qwen-long", {"api_key": "fake-test-key"}, messages(extension), {}, stream=False
                )
            )
    post.assert_not_called()
    get.assert_not_called()


def test_complete_encoded_body_accepts_32_mib_and_rejects_one_more_byte():
    instance = model()
    with patch("requests.post", side_effect=response) as post:
        list(
            instance.invoke(
                "qwen-long", {"api_key": "fake-test-key"}, messages(question=""), {}, stream=False
            )
        )
        overhead = len(post.call_args.kwargs["data"])
        post.reset_mock()
        list(
            instance.invoke(
                "qwen-long",
                {"api_key": "fake-test-key"},
                messages(question="x" * (REQUEST_BODY_LIMIT - overhead)),
                {},
                stream=False,
            )
        )
        assert len(post.call_args.kwargs["data"]) == REQUEST_BODY_LIMIT
        post.reset_mock()
        with pytest.raises(InvokeBadRequestError):
            list(
                instance.invoke(
                    "qwen-long",
                    {"api_key": "fake-test-key"},
                    messages(question="x" * (REQUEST_BODY_LIMIT - overhead + 1)),
                    {},
                    stream=False,
                )
            )
        post.assert_not_called()


def test_download_failure_does_not_send_a_text_only_request():
    with (
        patch("requests.get", side_effect=requests.ConnectionError("private signed URL")),
        patch("requests.post") as post,
    ):
        with pytest.raises(InvokeError) as error:
            list(
                model().invoke(
                    "qwen-long",
                    {"api_key": "fake-test-key"},
                    messages(url="https://example.invalid/document.pdf"),
                    {},
                    stream=False,
                )
            )
    assert "private signed URL" not in str(error.value)
    post.assert_not_called()


def test_structured_output_parameters_survive_document_requests():
    schema = {"name": "answer", "schema": {"type": "object", "properties": {}}}
    with patch("requests.post", side_effect=response) as post:
        list(
            model().invoke(
                "qwen-long",
                {"api_key": "fake-test-key"},
                messages(),
                {"response_format": "json_schema", "json_schema": json.dumps(schema)},
                stream=False,
            )
        )
    assert json.loads(post.call_args.kwargs["data"])["response_format"] == {
        "type": "json_schema",
        "json_schema": schema,
    }


def test_http_error_redacts_encoded_keys_custom_headers_and_bearer_before_auth_labels():
    key = "private key/+="
    opaque_header = "opaque-custom-header-secret"
    failed, close = error_response(
        401,
        json.dumps(
            {
                "error": {
                    "message": "Invalid private%20key%2F%2B%3D, opaque-custom-header-secret, "
                    "Bearer unknown-token-value, rk-other-value, tkr_other_value"
                }
            }
        ),
    )
    credentials = {
        "api_key": key,
        "auth_type": "Bearer",
        "extra_headers": {"X-Custom": opaque_header},
    }
    with patch("requests.post", return_value=failed):
        with pytest.raises(InvokeError) as error:
            list(model().invoke("qwen-long", credentials, messages(), {}, stream=False))
    message = str(error.value)
    for value in (
        key,
        "private%20key%2F%2B%3D",
        opaque_header,
        "unknown-token-value",
        "rk-other-value",
        "tkr_other_value",
    ):
        assert value not in message
    assert "HTTP 401" in message
    close.assert_called_once()
