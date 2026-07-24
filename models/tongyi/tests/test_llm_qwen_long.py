import base64
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm.llm import TongyiLargeLanguageModel
from models.llm.qwen_long import QwenLongFileUploader


def _document(filename: str = "report.pdf") -> DocumentPromptMessageContent:
    return DocumentPromptMessageContent(
        format="pdf",
        base64_data=base64.b64encode(b"document content").decode(),
        mime_type="application/pdf",
        filename=filename,
    )


def _model() -> TongyiLargeLanguageModel:
    return TongyiLargeLanguageModel(model_schemas=MagicMock())


def test_qwen_long_converts_document_to_system_file_id() -> None:
    model = _model()
    model._upload_file_to_tongyi = MagicMock(return_value="file-fe-123")

    messages = model._convert_qwen_long_prompt_messages(
        credentials={"dashscope_api_key": "test-key"},
        prompt_messages=[
            SystemPromptMessage(content="You are a document analyst."),
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="Summarize this document."),
                    _document(),
                ]
            ),
        ],
    )

    assert messages == [
        {"role": "system", "content": "You are a document analyst."},
        {"role": "system", "content": "fileid://file-fe-123"},
        {"role": "user", "content": "Summarize this document."},
    ]
    assert isinstance(messages[2]["content"], str)


def test_qwen_long_generate_sends_string_user_content() -> None:
    model = _model()
    model.get_model_mode = MagicMock(return_value="chat")
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=[ModelFeature.DOCUMENT])
    )
    model._upload_file_to_tongyi = MagicMock(return_value="file-fe-123")
    model._handle_generate_response = MagicMock(return_value="result")

    with patch(
        "models.llm.llm.Generation.call",
        return_value=MagicMock(),
    ) as call:
        result = model._generate(
            model="qwen-long",
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[
                SystemPromptMessage(content="You are a document analyst."),
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="Summarize this document."),
                        _document(),
                    ]
                ),
            ],
            model_parameters={},
            stream=False,
        )

    assert result == "result"
    messages = call.call_args.kwargs["messages"]
    assert messages == [
        {"role": "system", "content": "You are a document analyst."},
        {"role": "system", "content": "fileid://file-fe-123"},
        {"role": "user", "content": "Summarize this document."},
    ]
    assert isinstance(messages[2]["content"], str)


def test_qwen_long_injects_role_definition_for_document_input() -> None:
    model = _model()
    model._upload_file_to_tongyi = MagicMock(return_value="file-fe-123")

    messages = model._convert_qwen_long_prompt_messages(
        credentials={"dashscope_api_key": "test-key"},
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="Summarize this document."),
                    _document(),
                ]
            )
        ],
    )

    assert messages[0] == {
        "role": "system",
        "content": "You are a helpful assistant.",
    }
    assert messages[1] == {
        "role": "system",
        "content": "fileid://file-fe-123",
    }
    assert messages[2] == {
        "role": "user",
        "content": "Summarize this document.",
    }


def test_qwen_long_combines_multiple_file_ids() -> None:
    model = _model()
    model._upload_file_to_tongyi = MagicMock(side_effect=["file-fe-123", "file-fe-456"])

    messages = model._convert_qwen_long_prompt_messages(
        credentials={"dashscope_api_key": "test-key"},
        prompt_messages=[
            SystemPromptMessage(content="You are a document analyst."),
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="Compare these documents."),
                    _document("first.pdf"),
                    _document("second.pdf"),
                ]
            ),
        ],
    )

    assert messages[1] == {
        "role": "system",
        "content": "fileid://file-fe-123,fileid://file-fe-456",
    }
    assert messages[2] == {
        "role": "user",
        "content": "Compare these documents.",
    }


def test_qwen_long_rejects_document_without_question() -> None:
    model = _model()
    model._upload_file_to_tongyi = MagicMock(return_value="file-fe-123")

    with pytest.raises(InvokeBadRequestError, match="non-empty text question"):
        model._convert_qwen_long_prompt_messages(
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content=[_document()])],
        )


def test_qwen_long_file_uploader_waits_until_processed() -> None:
    client = MagicMock()
    client.files.create.return_value = SimpleNamespace(
        id="file-fe-123",
        status="processing",
    )
    client.files.retrieve.return_value = SimpleNamespace(
        id="file-fe-123",
        status="processed",
    )

    with patch("models.llm.qwen_long.time.sleep") as sleep:
        file_id = QwenLongFileUploader(client).upload(_document())

    assert file_id == "file-fe-123"
    client.files.retrieve.assert_called_once_with("file-fe-123")
    sleep.assert_called_once_with(5)
    upload = client.files.create.call_args.kwargs
    assert upload["purpose"] == "file-extract"
    assert upload["file"][0] == "report.pdf"
    assert upload["file"][2] == "application/pdf"


def test_qwen_long_file_uploader_reports_processing_error() -> None:
    client = MagicMock()
    client.files.create.return_value = SimpleNamespace(
        id="file-fe-123",
        status="error",
        status_details="invalid document",
    )

    with pytest.raises(ValueError, match="invalid document"):
        QwenLongFileUploader(client).upload(_document())


def test_qwen_long_file_uploader_times_out() -> None:
    client = MagicMock()
    client.files.create.return_value = SimpleNamespace(
        id="file-fe-123",
        status="processing",
    )

    with (
        patch(
            "models.llm.qwen_long.time.monotonic",
            side_effect=[0, 301],
        ),
        pytest.raises(TimeoutError, match="Timed out"),
    ):
        QwenLongFileUploader(client).upload(_document())

    client.files.retrieve.assert_not_called()


def test_qwen_long_model_metadata_matches_supported_features() -> None:
    model_file = Path(__file__).parent.parent / "models" / "llm" / "qwen-long.yaml"
    schema = yaml.safe_load(model_file.read_text())

    assert schema["features"] == ["document"]
    max_tokens = next(
        rule for rule in schema["parameter_rules"] if rule["name"] == "max_tokens"
    )
    assert max_tokens["max"] == 32768
