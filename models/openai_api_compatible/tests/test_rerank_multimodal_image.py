"""Regression tests for image handling in multimodal rerank.

Dify passes images to the plugin as raw base64 (no `data:` prefix). The
plugin used to
  * inline an image query into the text query as `[Image: <base64>]`, which
    overflows the model context window (HTTP 400 from vLLM), and
  * drop raw-base64 document images because they failed URL validation,
    leaving an empty `{"content": []}` document.

These tests capture the payload sent to the rerank endpoint.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import InvokeBadRequestError

from models.rerank.rerank import OpenAIRerankModel

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG_B64 = base64.b64encode(PNG_BYTES).decode()
JPEG_B64 = base64.b64encode(JPEG_BYTES).decode()

IMAGE = MultiModalContentType.IMAGE
TEXT = MultiModalContentType.TEXT


def _credentials():
    return {
        "endpoint_url": "https://rerank.example.com/v1",
        "api_key": "",
        "endpoint_model_name": "qwen3-vl-reranker",
    }


def _invoke(query, docs):
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"results": [{"index": 0, "relevance_score": 0.5}]},
        )
        result = model._invoke_multimodal(
            model="qwen3-vl-reranker",
            credentials=_credentials(),
            query=query,
            docs=docs,
        )
    assert mock_post.call_count == 1
    return mock_post.call_args.kwargs["json"], result


def test_image_query_is_sent_as_multimodal_param_not_text():
    payload, _ = _invoke(
        MultiModalContent(content_type=IMAGE, content=PNG_B64),
        [MultiModalContent(content_type=TEXT, content="doc")],
    )

    assert payload["query"] == {
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{PNG_B64}"},
            }
        ]
    }
    assert "[Image:" not in str(payload)


def test_text_query_is_still_sent_as_plain_string():
    payload, _ = _invoke(
        MultiModalContent(content_type=TEXT, content="hello"),
        [MultiModalContent(content_type=TEXT, content="doc")],
    )

    assert payload["query"] == "hello"


@pytest.mark.parametrize(
    ("raw_b64", "expected_format"),
    [(PNG_B64, "png"), (JPEG_B64, "jpeg")],
)
def test_raw_base64_document_image_gets_data_uri_prefix(raw_b64, expected_format):
    payload, _ = _invoke(
        MultiModalContent(content_type=TEXT, content="q"),
        [MultiModalContent(content_type=IMAGE, content=raw_b64)],
    )

    assert payload["documents"] == [
        {
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{expected_format};base64,{raw_b64}"
                    },
                }
            ]
        }
    ]


def test_existing_data_uri_and_https_url_are_left_unchanged():
    data_uri = f"data:image/png;base64,{PNG_B64}"
    https_url = "https://example.com/a.png"

    payload, _ = _invoke(
        MultiModalContent(content_type=TEXT, content="q"),
        [
            MultiModalContent(content_type=IMAGE, content=data_uri),
            MultiModalContent(content_type=IMAGE, content=https_url),
        ],
    )

    urls = [d["content"][0]["image_url"]["url"] for d in payload["documents"]]
    assert urls == [data_uri, https_url]


@pytest.mark.parametrize(
    "unsafe",
    [
        "file:///etc/passwd",
        "http://localhost/a.png",
        "http://10.0.0.1/a.png",
        "not-an-image",
    ],
)
def test_unsafe_or_invalid_document_images_are_still_dropped(unsafe):
    payload, _ = _invoke(
        MultiModalContent(content_type=TEXT, content="q"),
        [MultiModalContent(content_type=IMAGE, content=unsafe)],
    )

    assert payload["documents"] == [{"content": []}]


def test_invalid_image_query_raises_bad_request_without_calling_endpoint():
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        with pytest.raises(InvokeBadRequestError):
            model._invoke_multimodal(
                model="qwen3-vl-reranker",
                credentials=_credentials(),
                query=MultiModalContent(content_type=IMAGE, content="not-an-image"),
                docs=[MultiModalContent(content_type=TEXT, content="doc")],
            )

    mock_post.assert_not_called()
