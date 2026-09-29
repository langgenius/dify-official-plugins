from unittest.mock import MagicMock, patch

import pytest

from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import InvokeError

from models.text_embedding.text_embedding import OpenAITextEmbeddingModel


def _successful_embedding_response(
    embeddings: list[list[float]] | None = None,
) -> MagicMock:
    embeddings = embeddings or [[0.1, 0.2, 0.3]]
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [{"embedding": embedding} for embedding in embeddings],
        "usage": {"total_tokens": 3},
    }
    return response


def _credentials(**overrides):
    credentials = {
        "endpoint_url": "https://litellm.example.com/v1",
        "endpoint_model_name": "Qwen3-Embedding-8B",
        "api_key": "test-key",
        "context_size": "4096",
        "max_chunks": "8",
    }
    credentials.update(overrides)
    return credentials


@patch("models.text_embedding.text_embedding.requests.post")
def test_text_embedding_sends_configured_encoding_format(mock_post):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke(
        model="display-name", credentials=_credentials(encoding_format="float"), texts=["ping"]
    )

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {"model": "Qwen3-Embedding-8B", "input": ["ping"], "encoding_format": "float"}
    assert result.embeddings == [[0.1, 0.2, 0.3]]


@patch("models.text_embedding.text_embedding.requests.post")
def test_text_embedding_omits_unset_encoding_format(mock_post):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke(
        model="display-name", credentials=_credentials(encoding_format="not_set"), texts=["ping"]
    )

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {"model": "Qwen3-Embedding-8B", "input": ["ping"]}


@patch("models.text_embedding.text_embedding.requests.post")
def test_text_embedding_validate_credentials_uses_runtime_payload_shape(mock_post):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model.validate_credentials(
        model="display-name", credentials=_credentials(encoding_format="float")
    )

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {"model": "Qwen3-Embedding-8B", "input": ["ping"], "encoding_format": "float"}


@pytest.mark.parametrize("vision_support", ["no_support", "support"])
@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.requests.post")
def test_plain_text_containing_image_marker_uses_text_embedding(
    mock_post, mock_openai, vision_support
):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])
    text = "Docker Image: langgenius/dify-api:latest"

    result = model._invoke(
        model="display-name",
        credentials=_credentials(api_key="", vision_support=vision_support),
        texts=[text],
    )

    mock_openai.assert_not_called()
    assert mock_post.call_args.kwargs["json"] == {
        "model": "Qwen3-Embedding-8B",
        "input": [text],
    }
    assert result.embeddings == [[0.1, 0.2, 0.3]]


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.requests.post")
def test_markdown_image_in_text_is_not_promoted_to_multimodal(mock_post, mock_openai):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])
    text = "before ![image](http://192.168.1.100/files/id/file-preview) after"

    result = model._invoke(
        model="display-name",
        credentials=_credentials(vision_support="support"),
        texts=[text],
    )

    mock_openai.assert_not_called()
    assert mock_post.call_args.kwargs["json"] == {
        "model": "Qwen3-Embedding-8B",
        "input": [text],
    }
    assert result.embeddings == [[0.1, 0.2, 0.3]]


def _chat_embedding_response() -> MagicMock:
    response = MagicMock()
    response.data = [MagicMock(embedding=[0.4, 0.5, 0.6])]
    response.model_dump.return_value = {"usage": {"total_tokens": 5}}
    return response


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.create_chat_embeddings")
def test_multimodal_embedding_sends_endpoint_model_name(mock_create, _mock_openai):
    # Regression test for #3191: the multimodal (vision) path must send the
    # configured endpoint_model_name upstream, not the Dify display/registration
    # name, otherwise the upstream server returns 404.
    mock_create.return_value = _chat_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke_multimodal(
        model="Qwen3-VL-Embedding",
        credentials=_credentials(
            endpoint_model_name="qwen3-vl-embedding-8b-awq", vision_support="support"
        ),
        documents=[
            MultiModalContent(
                content_type=MultiModalContentType.IMAGE,
                content="iVBORw0KGgo=",
            )
        ],
    )

    assert mock_create.call_args.kwargs["model"] == "qwen3-vl-embedding-8b-awq"
    user_content = mock_create.call_args.kwargs["messages"][1]["content"]
    assert user_content[0] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
    }
    assert result.embeddings == [[0.4, 0.5, 0.6]]


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.create_chat_embeddings")
@patch("models.text_embedding.text_embedding.requests.post")
def test_multimodal_embedding_preserves_mixed_input_order(
    mock_post, mock_create, _mock_openai
):
    mock_post.side_effect = [
        _successful_embedding_response([[0.1, 0.0]]),
        _successful_embedding_response([[0.3, 0.0]]),
    ]
    mock_create.return_value = _chat_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke_multimodal(
        model="Qwen3-VL-Embedding",
        credentials=_credentials(vision_support="support"),
        documents=[
            MultiModalContent(
                content_type=MultiModalContentType.TEXT,
                content="first text",
            ),
            MultiModalContent(
                content_type=MultiModalContentType.IMAGE,
                content="iVBORw0KGgo=",
            ),
            MultiModalContent(
                content_type=MultiModalContentType.TEXT,
                content="second text",
            ),
        ],
    )

    assert [call.kwargs["json"]["input"] for call in mock_post.call_args_list] == [
        ["first text"],
        ["second text"],
    ]
    assert result.embeddings == [[0.1, 0.0], [0.4, 0.5, 0.6], [0.3, 0.0]]


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.create_chat_embeddings")
@patch("models.text_embedding.text_embedding.requests.post")
def test_multimodal_embedding_input_array_format_sends_data_uri(
    mock_post, mock_create, _mock_openai
):
    # Providers such as Gemini embedding endpoints and OpenAI-compatible gateways
    # (LiteLLM) reject the vLLM "messages" payload and take the image as a data URI
    # element of the standard "input" array.
    mock_post.return_value = _successful_embedding_response([[0.7, 0.8]])
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke_multimodal(
        model="gemini-embedding-2-preview",
        credentials=_credentials(
            vision_support="support", multimodal_embedding_format="input_array"
        ),
        documents=[
            MultiModalContent(
                content_type=MultiModalContentType.IMAGE,
                content="iVBORw0KGgo=",
            )
        ],
    )

    mock_create.assert_not_called()
    payload = mock_post.call_args.kwargs["json"]
    assert payload["input"] == ["data:image/png;base64,iVBORw0KGgo="]
    assert result.embeddings == [[0.7, 0.8]]


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.create_chat_embeddings")
@patch("models.text_embedding.text_embedding.requests.post")
def test_multimodal_embedding_input_array_format_preserves_mixed_input_order(
    mock_post, mock_create, _mock_openai
):
    mock_post.side_effect = [
        _successful_embedding_response([[0.1, 0.0]]),
        _successful_embedding_response([[0.3, 0.0]]),
        _successful_embedding_response([[0.7, 0.8]]),
    ]
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke_multimodal(
        model="gemini-embedding-2-preview",
        credentials=_credentials(
            vision_support="support", multimodal_embedding_format="input_array"
        ),
        documents=[
            MultiModalContent(
                content_type=MultiModalContentType.TEXT,
                content="first text",
            ),
            MultiModalContent(
                content_type=MultiModalContentType.IMAGE,
                content="iVBORw0KGgo=",
            ),
            MultiModalContent(
                content_type=MultiModalContentType.TEXT,
                content="second text",
            ),
        ],
    )

    mock_create.assert_not_called()
    assert [call.kwargs["json"]["input"] for call in mock_post.call_args_list] == [
        ["first text"],
        ["second text"],
        ["data:image/png;base64,iVBORw0KGgo="],
    ]
    assert result.embeddings == [[0.1, 0.0], [0.7, 0.8], [0.3, 0.0]]


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.create_chat_embeddings")
@patch("models.text_embedding.text_embedding.requests.post")
@pytest.mark.parametrize(
    "overrides",
    [{}, {"multimodal_embedding_format": "chat_embeddings"}, {"multimodal_embedding_format": "unknown"}],
    ids=["unset", "explicit", "unknown-value"],
)
def test_multimodal_embedding_defaults_to_chat_embeddings_format(
    mock_post, mock_create, _mock_openai, overrides
):
    # Servers implementing the vLLM chat embeddings extension keep working unchanged,
    # and an unrecognised value must not silently switch the wire format.
    mock_create.return_value = _chat_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke_multimodal(
        model="Qwen3-VL-Embedding",
        credentials=_credentials(vision_support="support", **overrides),
        documents=[
            MultiModalContent(
                content_type=MultiModalContentType.IMAGE,
                content="iVBORw0KGgo=",
            )
        ],
    )

    mock_create.assert_called_once()
    mock_post.assert_not_called()


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.requests.post")
def test_multimodal_input_array_sends_one_request_per_image(mock_post, _mock_openai):
    # Providers reached this way may fuse several input elements into a single
    # embedding, so each image must travel on its own request to stay 1:1.
    mock_post.side_effect = [
        _successful_embedding_response([[0.1, 0.1]]),
        _successful_embedding_response([[0.2, 0.2]]),
    ]
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke_multimodal(
        model="display-name",
        credentials=_credentials(
            vision_support="support",
            multimodal_embedding_format="input_array",
            encoding_format="float",
        ),
        documents=[
            MultiModalContent(content_type=MultiModalContentType.IMAGE, content="iVBORw0KGgo="),
            MultiModalContent(content_type=MultiModalContentType.IMAGE, content="R0lGODlh"),
        ],
    )

    assert mock_post.call_count == 2
    payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
    assert [payload["input"] for payload in payloads] == [
        ["data:image/png;base64,iVBORw0KGgo="],
        ["data:image/gif;base64,R0lGODlh"],
    ]
    # the configured upstream model id and encoding_format must reach every request
    assert {payload["model"] for payload in payloads} == {"Qwen3-Embedding-8B"}
    assert {payload["encoding_format"] for payload in payloads} == {"float"}
    assert result.embeddings == [[0.1, 0.1], [0.2, 0.2]]
    assert result.usage.tokens == 6


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.create_chat_embeddings")
@patch("models.text_embedding.text_embedding.requests.post")
def test_multimodal_embedding_rejects_undetectable_image_format(
    mock_post, mock_create, _mock_openai
):
    # An undetected format used to produce "data:image;base64,...", a data URI with no
    # subtype, which strict providers reject with an unrelated-looking error.
    model = OpenAITextEmbeddingModel(model_schemas=[])

    with pytest.raises(InvokeError, match="Could not detect the image format"):
        model._invoke_multimodal(
            model="display-name",
            credentials=_credentials(vision_support="support"),
            documents=[
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE,
                    content="dGhpcyBpcyBub3QgYW4gaW1hZ2U=",
                )
            ],
        )

    mock_post.assert_not_called()
    mock_create.assert_not_called()


@patch("models.text_embedding.text_embedding.OpenAI")
@patch("models.text_embedding.text_embedding.requests.post")
def test_multimodal_input_array_rejects_fused_response(mock_post, _mock_openai):
    # A provider answering one embedding for two inputs would otherwise shift every
    # following vector; fail loudly instead of storing mismatched embeddings.
    fused = _successful_embedding_response([[0.1, 0.1], [0.2, 0.2]])
    mock_post.return_value = fused
    model = OpenAITextEmbeddingModel(model_schemas=[])

    with pytest.raises(InvokeError, match="Expected 1 embedding for 1 input, got 2"):
        model._invoke_multimodal(
            model="display-name",
            credentials=_credentials(
                vision_support="support", multimodal_embedding_format="input_array"
            ),
            documents=[
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE, content="iVBORw0KGgo="
                )
            ],
        )
