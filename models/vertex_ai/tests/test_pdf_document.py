"""Regression tests for PDF document passthrough to Claude on Vertex AI.

Covers GitHub issue #4005: a user attaching a PDF to a Claude chat on
Vertex AI previously saw the file silently dropped because the document
content type was never serialized. These tests pin:

  * the new DOCUMENT branch in _convert_claude_prompt_message_to_dict emits
    the Anthropic base64 document shape Dify expects;
  * the helper rejects URL-only and non-PDF document sources rather than
    forwarding an ill-formed payload;
  * every Claude model yaml in models/llm/ declares the document feature
    so Dify forwards the PDF in the first place.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)

from models.llm.llm import VertexAiLargeLanguageModel

PDF_BASE64 = "JVBERi0xLjQKJcKlwrHDqwoKMSAwIG9iagogIDw8IC9UeXBlIC9DYXRhbG9nIC9QYWdlcyAyIDAgUj4+CmVuZG9iagoyIDAgb2JqCiAgPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAxIDAgUiAvUmVzb3VyY2VzIDw8ID4+IC9NZWRpYUJveCBbMCA0IDU5NSA4NDJdIC9Db250ZW50cyAzIDAgUiA+PgplbmRvYmoKMyAwIG9iago"

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
LLM_YAML_DIR = PLUGIN_ROOT / "models" / "llm"


def _instance() -> VertexAiLargeLanguageModel:
    """Build a bare _LargeLanguageModel instance without going through the dify_plugin runtime.

    VertexAiLargeLanguageModel.__init__ comes from LargeLanguageModel and
    only stores config, so types.SimpleNamespace() is a safe stand-in for
    the model_config positional arg.
    """
    return VertexAiLargeLanguageModel.__new__(VertexAiLargeLanguageModel)


def _user_message_with_document(
    *,
    base64_data: str = PDF_BASE64,
    mime_type: str = "application/pdf",
    url: str = "",
) -> UserPromptMessage:
    return UserPromptMessage(
        content=[
            TextPromptMessageContent(data="What is the secret word in this PDF?"),
            DocumentPromptMessageContent(
                format="pdf",
                base64_data=base64_data,
                mime_type=mime_type,
                url=url,
                filename="sample.pdf",
            ),
        ]
    )


def _convert(message: UserPromptMessage) -> dict[str, Any]:
    """Run only the per-message dispatcher; bypass _convert_claude_prompt_messages
    because that helper also strips system messages, which is not what these
    tests are about.
    """
    return _instance()._convert_claude_prompt_message_to_dict(message)


# ---------------------------------------------------------------------------
# Per-message dispatch (DOCUMENT branch)
# ---------------------------------------------------------------------------

def test_document_pdf_is_serialized_as_anthropic_base64_block():
    """The happy path: a PDF document is converted to an Anthropic document block."""
    result = _convert(_user_message_with_document())

    assert result["role"] == "user"
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) == 2

    # Text block is preserved as-is.
    assert content[0] == {"type": "text", "text": "What is the secret word in this PDF?"}

    # Document block matches the Anthropic Messages API shape for PDF input.
    document_block = content[1]
    assert document_block["type"] == "document"
    assert document_block["source"]["type"] == "base64"
    assert document_block["source"]["media_type"] == "application/pdf"
    assert document_block["source"]["data"] == PDF_BASE64


def test_document_block_preserves_order_with_text():
    """The DOCUMENT branch must append, not insert; the caller-supplied order survives."""
    result = _convert(_user_message_with_document())

    types_seen = [block["type"] for block in result["content"]]
    assert types_seen == ["text", "document"]


def test_document_url_source_is_rejected():
    """Claude on Vertex AI only accepts base64 document sources, not URLs."""
    message = UserPromptMessage(
        content=[
            DocumentPromptMessageContent(
                format="pdf",
                base64_data=PDF_BASE64,
                mime_type="application/pdf",
                url="https://example.com/secret.pdf",
                filename="secret.pdf",
            )
        ]
    )
    with pytest.raises(ValueError, match="URL-based document sources are not supported"):
        _convert(message)


def test_document_empty_base64_is_rejected():
    """A document with no payload cannot be forwarded; surface the failure."""
    message = UserPromptMessage(
        content=[
            DocumentPromptMessageContent(
                format="pdf",
                base64_data="",
                mime_type="application/pdf",
                url="",
                filename="empty.pdf",
            )
        ]
    )
    with pytest.raises(ValueError, match="Document content has no base64 payload"):
        _convert(message)


def test_document_non_pdf_mime_type_is_rejected():
    """Claude only accepts application/pdf for documents."""
    message = UserPromptMessage(
        content=[
            DocumentPromptMessageContent(
                format="docx",
                base64_data="UEsDBA==",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                url="",
                filename="report.docx",
            )
        ]
    )
    with pytest.raises(ValueError, match="only accepts application/pdf"):
        _convert(message)


def test_text_message_without_document_is_unchanged():
    """The new branch must not perturb pre-existing TEXT-only behavior."""
    message = UserPromptMessage(content="Just a text question.")
    result = _convert(message)
    assert result == {"role": "user", "content": "Just a text question."}


# ---------------------------------------------------------------------------
# Source-level guards — pin the dispatch helper's shape
# ---------------------------------------------------------------------------

def test_llm_imports_document_prompt_message_content():
    """The new branch casts to DocumentPromptMessageContent, so the import must exist."""
    source = (PLUGIN_ROOT / "models" / "llm" / "llm.py").read_text()
    assert "DocumentPromptMessageContent" in source
    # And it must come from dify_plugin (not a local redefinition).
    assert "from dify_plugin.entities.model.message import" in source
    # Pull out the import block to ensure DocumentPromptMessageContent is in it.
    import_block = source.split("from dify_plugin.entities.model.message import", 1)[1].split(")", 1)[0]
    assert "DocumentPromptMessageContent" in import_block


def test_llm_handles_prompt_message_content_type_document():
    """The dispatcher must branch on PromptMessageContentType.DOCUMENT."""
    source = (PLUGIN_ROOT / "models" / "llm" / "llm.py").read_text()
    assert "PromptMessageContentType.DOCUMENT" in source


def test_llm_emits_anthropic_document_source_shape():
    """The emitted block must match Anthropic's base64 document source shape."""
    source = (PLUGIN_ROOT / "models" / "llm" / "llm.py").read_text()
    assert '"type": "document"' in source
    assert '"source"' in source
    assert '"media_type"' in source
    # base64 must appear as a string literal, not a placeholder.
    assert '"base64"' in source


# ---------------------------------------------------------------------------
# YAML feature guards — every Claude model that supports PDF must declare it
# ---------------------------------------------------------------------------

CLAUDE_YAMLS = sorted(
    path.name
    for path in LLM_YAML_DIR.glob("anthropic.claude-*.yaml")
)


def test_claude_yaml_set_is_stable():
    """Pin the inventory so a rename or accidental delete surfaces as a test failure."""
    expected = {
        "anthropic.claude-3-haiku.yaml",
        "anthropic.claude-3-opus.yaml",
        "anthropic.claude-3-sonnet.yaml",
        "anthropic.claude-3.5-sonnet.yaml",
        "anthropic.claude-3.5-sonnet-v2.yaml",
        "anthropic.claude-3.7-sonnet.yaml",
        "anthropic.claude-haiku-4-5.yaml",
        "anthropic.claude-opus-4.yaml",
        "anthropic.claude-opus-4-5.yaml",
        "anthropic.claude-opus-4-6.yaml",
        "anthropic.claude-opus-4-7.yaml",
        "anthropic.claude-opus-4-8.yaml",
        "anthropic.claude-sonnet-4.yaml",
        "anthropic.claude-sonnet-4-5.yaml",
        "anthropic.claude-sonnet-4-6.yaml",
        "anthropic.claude-sonnet-5.yaml",
    }
    assert set(CLAUDE_YAMLS) == expected


@pytest.mark.parametrize("yaml_name", CLAUDE_YAMLS)
def test_claude_yaml_declares_document_feature(yaml_name: str):
    """Every Claude model that supports PDF on Vertex AI must declare the document feature,
    otherwise Dify strips PDFs from the prompt before the plugin is called and the new
    DOCUMENT branch never has a chance to fire.
    """
    text = (LLM_YAML_DIR / yaml_name).read_text()
    assert "\n  - document\n" in text, (
        f"{yaml_name} must declare the `document` feature so Dify forwards PDFs to the plugin"
    )