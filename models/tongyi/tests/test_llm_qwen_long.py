import base64
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DocumentPromptMessageContent,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeServerUnavailableError,
)

from models.llm.llm import TongyiLargeLanguageModel
from models.llm.qwen_long import QwenLongFiles


def _document(
    filename: str = "report.pdf",
    data: bytes = b"document content",
) -> DocumentPromptMessageContent:
    return DocumentPromptMessageContent(
        format="pdf",
        base64_data=base64.b64encode(data).decode(),
        mime_type="application/pdf",
        filename=filename,
    )


def _model() -> TongyiLargeLanguageModel:
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    model.get_model_mode = MagicMock(return_value="chat")
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=[ModelFeature.DOCUMENT])
    )
    return model


def _client() -> MagicMock:
    client = MagicMock()
    client.files.create.return_value = SimpleNamespace(id="file-fe-123")
    client.files.wait_for_processing.return_value = SimpleNamespace(
        id="file-fe-123",
        status="processed",
    )
    client.files.delete.return_value = SimpleNamespace(deleted=True)
    return client


def test_qwen_long_generate_normalizes_graphon_split_input_and_cleans_up() -> None:
    model = _model()
    model._handle_generate_response = MagicMock(return_value="result")
    client = _client()

    with (
        patch("models.llm.llm.openai.OpenAI", return_value=client) as openai_client,
        patch("models.llm.llm.Generation.call", return_value=MagicMock()) as call,
    ):
        result = model._generate(
            model="qwen-long",
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[
                SystemPromptMessage(content="You are a document analyst."),
                UserPromptMessage(content="Summarize this document."),
                UserPromptMessage(content=[_document()]),
            ],
            model_parameters={},
            stream=False,
        )

    assert result == "result"
    openai_client.assert_called_once_with(
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        max_retries=0,
        timeout=120,
    )
    assert call.call_args.kwargs["messages"] == [
        {"role": "system", "content": "You are a document analyst."},
        {"role": "system", "content": "fileid://file-fe-123"},
        {"role": "user", "content": "Summarize this document."},
    ]
    client.files.delete.assert_called_once_with("file-fe-123", timeout=10)
    client.close.assert_called_once()


def test_qwen_long_keeps_documents_in_their_conversation_turn() -> None:
    model = _model()
    files = MagicMock(spec=QwenLongFiles)
    files.upload.side_effect = ["file-fe-1", "file-fe-2"]

    messages = model._convert_qwen_long_prompt_messages(
        files,
        [
            UserPromptMessage(content=[_document("first.pdf")]),
            UserPromptMessage(content="Summarize the first document."),
            AssistantPromptMessage(content="First summary."),
            UserPromptMessage(
                content=[
                    _document("second.pdf"),
                    TextPromptMessageContent(data="Compare both documents."),
                ]
            ),
        ],
    )

    assert messages == [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "system", "content": "fileid://file-fe-1"},
        {"role": "user", "content": "Summarize the first document."},
        {"role": "assistant", "content": "First summary."},
        {"role": "system", "content": "fileid://file-fe-2"},
        {"role": "user", "content": "Compare both documents."},
    ]
    files.wait_until_processed.assert_called_once()


def test_qwen_long_rejects_document_without_question_before_upload() -> None:
    model = _model()
    files = MagicMock(spec=QwenLongFiles)

    with pytest.raises(InvokeBadRequestError, match="non-empty text question"):
        model._convert_qwen_long_prompt_messages(
            files,
            [UserPromptMessage(content=[_document()])],
        )

    files.upload.assert_not_called()


def test_qwen_long_rejects_system_document_before_upload() -> None:
    model = _model()
    files = MagicMock(spec=QwenLongFiles)

    with pytest.raises(InvokeBadRequestError, match="text system messages"):
        model._convert_qwen_long_prompt_messages(
            files,
            [
                SystemPromptMessage(content=[_document()]),
                UserPromptMessage(content="Summarize."),
            ],
        )

    files.upload.assert_not_called()


def test_qwen_long_rejects_more_than_100_documents_before_upload() -> None:
    model = _model()
    files = MagicMock(spec=QwenLongFiles)

    with pytest.raises(InvokeBadRequestError, match="at most 100"):
        model._convert_qwen_long_prompt_messages(
            files,
            [
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="Compare the documents."),
                        *[_document(f"{index}.pdf") for index in range(101)],
                    ]
                )
            ],
        )

    files.upload.assert_not_called()


def test_qwen_long_rejects_aggregate_document_size_before_upload() -> None:
    model = _model()
    files = MagicMock(spec=QwenLongFiles)

    with (
        patch("models.llm.llm.MAX_DOCUMENT_INPUT_BASE64_BYTES", 7),
        pytest.raises(InvokeBadRequestError, match="aggregate size"),
    ):
        model._convert_qwen_long_prompt_messages(
            files,
            [
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="Compare."),
                        _document("first.pdf", b"a"),
                        _document("second.pdf", b"b"),
                    ]
                )
            ],
        )

    files.upload.assert_not_called()


def test_qwen_long_files_uploads_with_metadata_and_shared_wait() -> None:
    client = _client()
    captured = {}

    def create(*, file, purpose):
        captured["filename"] = file[0]
        captured["payload"] = file[1].read()
        captured["mime_type"] = file[2]
        captured["purpose"] = purpose
        return SimpleNamespace(id="file-fe-123")

    client.files.create.side_effect = create
    files = QwenLongFiles(client)

    with patch(
        "models.llm.qwen_long.time.monotonic",
        side_effect=[100, 101],
    ):
        assert files.upload(_document()) == "file-fe-123"
        files.wait_until_processed()

    assert captured == {
        "filename": "report.pdf",
        "payload": b"document content",
        "mime_type": "application/pdf",
        "purpose": "file-extract",
    }
    client.files.wait_for_processing.assert_called_once_with(
        "file-fe-123",
        poll_interval=5,
        max_wait_seconds=239,
    )


def test_qwen_long_files_roughly_spaces_shared_api_requests() -> None:
    client = _client()
    client.files.create.side_effect = [
        SimpleNamespace(id="file-fe-1"),
        SimpleNamespace(id="file-fe-2"),
    ]
    files = QwenLongFiles(client)

    with patch("models.llm.qwen_long.time.sleep") as sleep:
        files.upload(_document("first.pdf"))
        files.upload(_document("second.pdf"))
        files.wait_until_processed()
        files.cleanup()

    assert sleep.call_args_list == [call(0.35), call(0.1), call(0.1)]
    assert client.files.delete.call_args_list == [
        call("file-fe-1", timeout=10),
        call("file-fe-2", timeout=10),
    ]


def test_qwen_long_files_retries_failed_cleanup_once() -> None:
    client = _client()
    client.files.delete.side_effect = [
        SimpleNamespace(deleted=False),
        SimpleNamespace(deleted=True),
    ]
    files = QwenLongFiles(client)
    files.upload(_document())

    with patch("models.llm.qwen_long.time.sleep") as sleep:
        files.cleanup()

    assert client.files.delete.call_count == 2
    sleep.assert_called_once_with(0.1)
    client.close.assert_called_once()


@pytest.mark.parametrize("status", ["error", "deleted"])
def test_qwen_long_files_rejects_failed_processing_status(status: str) -> None:
    client = _client()
    client.files.wait_for_processing.return_value = SimpleNamespace(
        id="file-fe-123",
        status=status,
        status_details="invalid document",
    )
    files = QwenLongFiles(client)
    files.upload(_document())

    with pytest.raises(InvokeBadRequestError, match=status):
        files.wait_until_processed()


def test_qwen_long_files_maps_processing_timeout() -> None:
    client = _client()
    client.files.wait_for_processing.side_effect = RuntimeError("timeout")
    files = QwenLongFiles(client)
    files.upload(_document())

    with pytest.raises(InvokeServerUnavailableError, match="Timed out"):
        files.wait_until_processed()


def test_qwen_long_files_rejects_invalid_base64_before_upload() -> None:
    client = _client()
    files = QwenLongFiles(client)
    document = DocumentPromptMessageContent(
        format="pdf",
        base64_data="not-base64",
        mime_type="application/pdf",
        filename="report.pdf",
    )

    with pytest.raises(InvokeBadRequestError, match="invalid base64"):
        files.upload(document)

    client.files.create.assert_not_called()


def test_qwen_long_files_rejects_padding_before_the_final_base64_chunk() -> None:
    client = _client()
    files = QwenLongFiles(client)
    document = DocumentPromptMessageContent(
        format="pdf",
        base64_data="YQ==Yg==",
        mime_type="application/pdf",
        filename="report.pdf",
    )

    with (
        patch("models.llm.qwen_long.FILE_READ_CHUNK_BYTES", 4),
        pytest.raises(InvokeBadRequestError, match="invalid base64"),
    ):
        files.upload(document)

    client.files.create.assert_not_called()


def test_qwen_long_files_rejects_oversized_base64_before_upload() -> None:
    client = _client()
    files = QwenLongFiles(client)

    with (
        patch("models.llm.qwen_long.DOCUMENT_MAX_BYTES", 3),
        pytest.raises(InvokeBadRequestError, match="file size"),
    ):
        files.upload(_document(data=b"four"))

    client.files.create.assert_not_called()


def test_qwen_long_files_rejects_url_input_before_upload() -> None:
    client = _client()
    files = QwenLongFiles(client)
    document = DocumentPromptMessageContent(
        format="pdf",
        url="https://example.com/report.pdf",
        mime_type="application/pdf",
        filename="report.pdf",
    )

    with pytest.raises(InvokeBadRequestError, match="requires base64"):
        files.upload(document)

    client.files.create.assert_not_called()


def test_qwen_long_cleans_up_when_processing_fails() -> None:
    model = _model()
    client = _client()
    client.files.wait_for_processing.return_value = SimpleNamespace(
        id="file-fe-123",
        status="error",
    )

    with (
        patch("models.llm.llm.openai.OpenAI", return_value=client),
        patch("models.llm.llm.Generation.call") as call,
        pytest.raises(InvokeBadRequestError, match="status error"),
    ):
        model._generate(
            model="qwen-long",
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="Summarize."),
                        _document(),
                    ]
                )
            ],
            model_parameters={},
            stream=False,
        )

    call.assert_not_called()
    client.files.delete.assert_called_once_with("file-fe-123", timeout=10)
    client.close.assert_called_once()


def test_qwen_long_cleans_up_when_invocation_is_cancelled() -> None:
    class Cancellation(BaseException):
        pass

    model = _model()
    client = _client()

    with (
        patch("models.llm.llm.openai.OpenAI", return_value=client),
        patch("models.llm.llm.Generation.call", side_effect=Cancellation),
        pytest.raises(Cancellation),
    ):
        model._generate(
            model="qwen-long",
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="Summarize."),
                        _document(),
                    ]
                )
            ],
            model_parameters={},
            stream=False,
        )

    client.files.delete.assert_called_once_with("file-fe-123", timeout=10)
    client.close.assert_called_once()


def test_qwen_long_stream_cleanup_waits_for_stream_completion() -> None:
    model = _model()
    model._handle_generate_stream_response = MagicMock(
        return_value=iter(["first", "second"])
    )
    client = _client()

    with (
        patch("models.llm.llm.openai.OpenAI", return_value=client),
        patch("models.llm.llm.Generation.call", return_value=MagicMock()),
    ):
        result = model._generate(
            model="qwen-long",
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="Summarize."),
                        _document(),
                    ]
                )
            ],
            model_parameters={},
            stream=True,
        )

        client.files.delete.assert_not_called()
        assert list(result) == ["first", "second"]

    client.files.delete.assert_called_once_with("file-fe-123", timeout=10)
    client.close.assert_called_once()


def test_qwen_long_rejects_international_endpoint_before_upload() -> None:
    model = _model()

    with (
        patch("models.llm.llm.openai.OpenAI") as openai,
        patch("models.llm.llm.Generation.call") as call,
        pytest.raises(InvokeBadRequestError, match="Beijing"),
    ):
        model._generate(
            model="qwen-long",
            credentials={
                "dashscope_api_key": "test-key",
                "use_international_endpoint": "true",
            },
            prompt_messages=[UserPromptMessage(content="Hello.")],
            model_parameters={},
            stream=False,
        )

    openai.assert_not_called()
    call.assert_not_called()


def test_qwen_long_preserves_standard_invoke_errors() -> None:
    error = InvokeBadRequestError("invalid input")

    assert _model()._transform_invoke_error(error) is error


def test_tongyi_import_patches_gevent_before_http_sdks() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import warnings; "
                "from gevent.monkey import MonkeyPatchWarning; "
                "warnings.simplefilter('error', MonkeyPatchWarning); "
                "import models.llm.llm"
            ),
        ],
        check=True,
    )
