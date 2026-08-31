"""Regression test for #3696.

VIDEO content was serialized as an OpenAI-compatible
\`image_url\` content part carrying a data URI. That broke
vLLM / LiteLLM-hosted_vllm backends that define a separate
\`video_url\` content part — they tried to decode the URI as an
image, got a wrong MIME, and returned HTTP 400 "cannot identify
image file". The fix routes VIDEO content through \`video_url\`
instead of \`image_url\`; the data URI itself is unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the model importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dify_plugin.entities.model.message import (
    UserPromptMessage,
    ImagePromptMessageContent,
    VideoPromptMessageContent,
    AudioPromptMessageContent,
    DocumentPromptMessageContent,
    PromptMessageContentType,
)
from models.llm.llm import OpenAILargeLanguageModel


def test_video_content_serializes_as_video_url_not_image_url():
    """VIDEO content must use the video_url content part. The previous
    image_url + data:video/...;base64, URI was rejected by vLLM-class
    backends (HTTP 400 "cannot identify image file")."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    video_c = VideoPromptMessageContent(
        type=PromptMessageContentType.VIDEO,
        format="data",
        base64_data="AAAA",
        mime_type="video/mp4",
    )
    msg = UserPromptMessage(content=[video_c])
    rendered = model._convert_prompt_message_to_dict(msg)

    parts = rendered["content"]
    assert len(parts) == 1
    part = parts[0]
    assert part["type"] == "video_url", f"expected video_url, got {part['type']}"
    assert part["video_url"] == {"url": "data:video/mp4;base64,AAAA"}
    # Defensive: must not regress to image_url (the bug we fixed).
    assert "image_url" not in part


def test_image_content_still_serializes_as_image_url():
    """The fix only routes VIDEO through video_url. IMAGE content
    must keep its image_url part so existing image-only providers
    aren't affected."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    image_c = ImagePromptMessageContent(
        type=PromptMessageContentType.IMAGE,
        format="data",
        base64_data="AAAA",
        mime_type="image/png",
        
    )
    msg = UserPromptMessage(content=[image_c])
    rendered = model._convert_prompt_message_to_dict(msg)

    part = rendered["content"][0]
    assert part["type"] == "image_url"
    assert part["image_url"] == {
        "url": "data:image/png;base64,AAAA",
        "detail": "low",
    }


def test_audio_content_still_serializes_as_image_url():
    """The fix leaves AUDIO on image_url. Some providers accept
    input_audio instead, but image_url with an audio MIME is the
    conservative default that Vertex Gemini and others convert to
    inline_data. Regression-only assertion."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    audio_c = AudioPromptMessageContent(
        type=PromptMessageContentType.AUDIO,
        format="data",
        base64_data="AAAA",
        mime_type="audio/mpeg",
    )
    msg = UserPromptMessage(content=[audio_c])
    rendered = model._convert_prompt_message_to_dict(msg)

    part = rendered["content"][0]
    assert part["type"] == "image_url"
    assert part["image_url"] == {"url": "data:audio/mpeg;base64,AAAA"}


def test_document_content_still_serializes_as_file():
    """DOCUMENT content uses the OpenAI Files-compatible file part
    with file_data set to the data URI. The fix leaves this path
    untouched — it's already correct for the providers that accept
    the file content part."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    doc_c = DocumentPromptMessageContent(
        type=PromptMessageContentType.DOCUMENT,
        format="data",
        base64_data="AAAA",
        mime_type="application/pdf",
        filename="spec.pdf",
    )
    msg = UserPromptMessage(content=[doc_c])
    rendered = model._convert_prompt_message_to_dict(msg)

    part = rendered["content"][0]
    assert part["type"] == "file"
    assert part["file"] == {
        "file_data": "data:application/pdf;base64,AAAA",
        "filename": "spec.pdf",
    }
