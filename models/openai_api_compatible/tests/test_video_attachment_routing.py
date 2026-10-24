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


def test_video_url_form_serializes_as_video_url():
    """VIDEO content referenced by URL (not base64) must also route
    through ``video_url`` -- the routing is keyed on the content
    type, not on whether the data is inline or remote. vLLM and
    LiteLLM-hosted_vllm accept both forms behind the ``video_url``
    content part; the previous ``image_url``+URL shape was rejected
    the same way as the data-URI shape."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    video_c = VideoPromptMessageContent(
        type=PromptMessageContentType.VIDEO,
        format="url",
        url="https://example.com/clip.mp4",
        mime_type="video/mp4",
    )
    msg = UserPromptMessage(content=[video_c])
    rendered = model._convert_prompt_message_to_dict(msg)

    part = rendered["content"][0]
    assert part["type"] == "video_url"
    assert part["video_url"] == {"url": "https://example.com/clip.mp4"}
    # Defensive: URL-form video must not regress to image_url either.
    assert "image_url" not in part


def test_video_does_not_use_image_url_data_uri_for_litellm_gemini_path():
    """Intentional divergence from the #3090 LiteLLM/Vertex-Gemini path.

    #3090 serialised VIDEO as an ``image_url`` content part carrying a
    data URI because LiteLLM would convert ``image_url`` to Gemini's
    ``inline_data`` block. That worked for Vertex Gemini via LiteLLM
    but was rejected by vLLM / LiteLLM-hosted_vllm (no image decoder
    for the video MIME -> HTTP 400 "cannot identify image file").

    The fix intentionally trades the LiteLLM/Vertex-Gemini path for
    the OpenAI-standard ``video_url`` path, which is what vLLM and
    any other backend that follows the OpenAI content-part spec
    expect. Vertex Gemini users on LiteLLM can route through
    ``hosted_vllm`` or use a vLLM backend instead.

    This test pins that the plugin does NOT silently fall back to the
    old ``image_url`` shape for video -- if a future refactor reintroduces
    it, this test will fail and the trade-off will need to be re-evaluated.
    """
    model = OpenAILargeLanguageModel(model_schemas=[])

    video_c = VideoPromptMessageContent(
        type=PromptMessageContentType.VIDEO,
        format="data",
        base64_data="AAAA",
        mime_type="video/mp4",
    )
    msg = UserPromptMessage(content=[video_c])
    rendered = model._convert_prompt_message_to_dict(msg)

    # The single content part must be video_url, not image_url.
    parts = rendered["content"]
    assert len(parts) == 1
    assert parts[0]["type"] != "image_url", (
        "VIDEO must not serialise as image_url -- that was the "
        "LiteLLM/Vertex-Gemini workaround from #3090 which vLLM rejects"
    )


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
