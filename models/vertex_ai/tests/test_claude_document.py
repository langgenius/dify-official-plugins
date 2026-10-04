import base64
from pathlib import Path

import pytest
import requests
import yaml
from anthropic.types import Message, TextBlock, Usage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DocumentPromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)

import models.llm.llm as llm_module
from models.llm.llm import VertexAiLargeLanguageModel

PDF_BYTES = b"%PDF-1.4 test"
PDF_BASE64 = base64.b64encode(PDF_BYTES).decode()
LLM_DIR = Path(__file__).resolve().parent.parent / "models" / "llm"


def _pdf(**kwargs) -> DocumentPromptMessageContent:
    params = {"format": "pdf", "mime_type": "application/pdf", "filename": "a.pdf"}
    params.update(kwargs)
    return DocumentPromptMessageContent(**params)


def _docx() -> DocumentPromptMessageContent:
    return DocumentPromptMessageContent(
        format="docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        base64_data="eA==",
        filename="b.docx",
    )


def _convert(messages):
    return VertexAiLargeLanguageModel([])._convert_claude_prompt_messages(messages)[1]


def test_pdf_is_sent_as_base64_document_block():
    messages = _convert(
        [
            UserPromptMessage(
                content=[TextPromptMessageContent(data="summarize"), _pdf(base64_data=PDF_BASE64)]
            )
        ]
    )
    assert messages == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "summarize"},
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": PDF_BASE64,
                    },
                },
            ],
        }
    ]


def test_pdf_url_is_downloaded_because_vertex_only_accepts_base64(monkeypatch):
    class FakeResponse:
        content = PDF_BYTES

        def raise_for_status(self):
            pass

    requested = []

    def fake_get(url, timeout=None):
        requested.append((url, timeout))
        return FakeResponse()

    monkeypatch.setattr(llm_module.requests, "get", fake_get)
    messages = _convert([UserPromptMessage(content=[_pdf(url="https://files.example/a.pdf")])])
    assert requested == [("https://files.example/a.pdf", llm_module.DOCUMENT_FETCH_TIMEOUT_SECONDS)]
    assert messages[0]["content"][0]["source"]["data"] == PDF_BASE64


def test_pdf_url_fetch_failure_raises(monkeypatch):
    def fake_get(url, timeout=None):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(llm_module.requests, "get", fake_get)
    with pytest.raises(ValueError, match="Failed to fetch document data"):
        _convert([UserPromptMessage(content=[_pdf(url="https://files.example/a.pdf")])])


def test_non_pdf_document_in_latest_message_raises():
    with pytest.raises(ValueError, match="only support application/pdf"):
        _convert([UserPromptMessage(content=[TextPromptMessageContent(data="read"), _docx()])])


def test_non_pdf_document_in_history_becomes_placeholder_text():
    messages = _convert(
        [
            UserPromptMessage(content=[TextPromptMessageContent(data="read"), _docx()]),
            AssistantPromptMessage(content="I can't read that file."),
            UserPromptMessage(content="ok, just say hi"),
        ]
    )
    assert messages[0]["content"][1] == {
        "type": "text",
        "text": "[Unsupported document: b.docx (application/vnd.openxmlformats-officedocument.wordprocessingml.document)]",
    }


def test_pdf_reaches_the_vertex_request(monkeypatch):
    sent = []

    class FakeMessages:
        def create(self, **kwargs):
            sent.append(kwargs)
            return Message(
                id="msg_test",
                type="message",
                role="assistant",
                model=kwargs["model"],
                content=[TextBlock(type="text", text="ok")],
                stop_reason="end_turn",
                stop_sequence=None,
                usage=Usage(input_tokens=1, output_tokens=1),
            )

    class FakeAnthropicVertex:
        def __init__(self, region, project_id, access_token=None):
            self.messages = FakeMessages()

    monkeypatch.setattr(llm_module, "AnthropicVertex", FakeAnthropicVertex)
    VertexAiLargeLanguageModel([])._generate_anthropic(
        "claude-sonnet-4-6",
        {
            "vertex_project_id": "proj",
            "vertex_location": "us-east5",
            "vertex_anthropic_location": "us-east5",
        },
        [
            UserPromptMessage(
                content=[TextPromptMessageContent(data="summarize"), _pdf(base64_data=PDF_BASE64)]
            )
        ],
        {"max_tokens": 16},
        stream=False,
    )
    assert [c["type"] for c in sent[0]["messages"][0]["content"]] == ["text", "document"]


@pytest.mark.parametrize("path", sorted(LLM_DIR.glob("anthropic.*.yaml")), ids=lambda p: p.name)
def test_claude_models_declare_document_support(path):
    # Claude 3 models and the first Claude 3.5 Sonnet never supported PDF input.
    no_pdf = {
        "anthropic.claude-3-haiku.yaml",
        "anthropic.claude-3-opus.yaml",
        "anthropic.claude-3-sonnet.yaml",
        "anthropic.claude-3.5-sonnet.yaml",
    }
    features = yaml.safe_load(path.read_text())["features"]
    assert ("document" in features) == (path.name not in no_pdf)
