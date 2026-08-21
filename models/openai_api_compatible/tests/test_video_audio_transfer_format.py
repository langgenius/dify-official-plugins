"""Tests for the ``video_transfer_format`` and ``audio_transfer_format``
credentials that control how VIDEO and AUDIO content is sent to
OpenAI-compatible servers.

The default (``image_url_data_uri``) packs video/audio as a data URI
under an ``image_url`` part, which LiteLLM dispatches into Vertex
Gemini's ``inline_data``. Servers that implement the OpenAI multimodal
spec (vLLM, LiteLLM ``hosted_vllm``) instead expect ``video_url`` and
``input_audio`` parts; sending ``image_url`` to those servers produces
a 400 ``Failed to load image`` error.

These tests pin both the default and the alternate wire formats for
VIDEO and AUDIO content. They also confirm that IMAGE content is
unaffected (image_url is always the right choice for images).
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.entities.model.message import (  # noqa: E402
    AudioPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from models.llm.llm import OpenAILargeLanguageModel  # noqa: E402


def _video_part() -> VideoPromptMessageContent:
    return VideoPromptMessageContent(
        mime_type="video/mp4",
        base64_data="AAAA",
        format="mp4",
    )


def _audio_part() -> AudioPromptMessageContent:
    return AudioPromptMessageContent(
        mime_type="audio/wav",
        base64_data="BBBB",
        format="wav",
    )


def _image_part() -> ImagePromptMessageContent:
    return ImagePromptMessageContent(
        mime_type="image/png",
        base64_data="CCCC",
        format="high",  # required by MultiModalPromptMessageContent; image uses detail value
        detail=ImagePromptMessageContent.DETAIL.HIGH,
    )


# Expected data URLs produced by MultiModalPromptMessageContent.data
VIDEO_DATA_URL = "data:video/mp4;base64,AAAA"
AUDIO_DATA_URL = "data:audio/wav;base64,BBBB"
IMAGE_DATA_URL = "data:image/png;base64,CCCC"


def _convert(message: UserPromptMessage, credentials: dict | None = None) -> dict:
    model = OpenAILargeLanguageModel(model_schemas=[])
    return model._convert_prompt_message_to_dict(message, credentials)


# ---------------------------------------------------------------------------
# Default behavior (image_url_data_uri) — must not regress
# ---------------------------------------------------------------------------


class TestDefaultImageUrlDataUri:
    """Without the new credentials, or with the default value, the
    wire format is the historical ``image_url`` data URI. This is
    required for Vertex Gemini via LiteLLM.
    """

    def test_video_uses_image_url_when_credential_omitted(self) -> None:
        msg = UserPromptMessage(content=[_video_part()])
        result = _convert(msg, credentials=None)
        assert result["content"] == [{"type": "image_url", "image_url": {"url": VIDEO_DATA_URL}}]

    def test_video_uses_image_url_when_credential_is_default(self) -> None:
        msg = UserPromptMessage(content=[_video_part()])
        result = _convert(msg, credentials={"video_transfer_format": "image_url_data_uri"})
        assert result["content"] == [{"type": "image_url", "image_url": {"url": VIDEO_DATA_URL}}]

    def test_audio_uses_image_url_when_credential_omitted(self) -> None:
        msg = UserPromptMessage(content=[_audio_part()])
        result = _convert(msg, credentials=None)
        assert result["content"] == [{"type": "image_url", "image_url": {"url": AUDIO_DATA_URL}}]

    def test_audio_uses_image_url_when_credential_is_default(self) -> None:
        msg = UserPromptMessage(content=[_audio_part()])
        result = _convert(msg, credentials={"audio_transfer_format": "image_url_data_uri"})
        assert result["content"] == [{"type": "image_url", "image_url": {"url": AUDIO_DATA_URL}}]

    def test_image_content_is_always_image_url(self) -> None:
        """The new credentials must not affect IMAGE content."""
        msg = UserPromptMessage(content=[_image_part()])
        result = _convert(
            msg,
            credentials={
                "video_transfer_format": "video_url",
                "audio_transfer_format": "input_audio",
            },
        )
        assert result["content"] == [
            {
                "type": "image_url",
                "image_url": {"url": IMAGE_DATA_URL, "detail": "high"},
            }
        ]


# ---------------------------------------------------------------------------
# OpenAI multimodal spec wire format (video_url / input_audio)
# ---------------------------------------------------------------------------


class TestVideoUrlFormat:
    """When ``video_transfer_format=video_url``, VIDEO content is sent
    as a ``video_url`` part with the data URI. This is the shape
    OpenAI-compatible servers implementing the OpenAI multimodal spec
    (vLLM, LiteLLM ``hosted_vllm``) accept.
    """

    def test_video_uses_video_url_part(self) -> None:
        msg = UserPromptMessage(content=[_video_part()])
        result = _convert(msg, credentials={"video_transfer_format": "video_url"})
        assert result["content"] == [{"type": "video_url", "video_url": {"url": VIDEO_DATA_URL}}]

    def test_video_url_format_does_not_change_audio(self) -> None:
        """Setting video_transfer_format must not affect audio."""
        msg = UserPromptMessage(content=[_audio_part()])
        result = _convert(msg, credentials={"video_transfer_format": "video_url"})
        assert result["content"][0]["type"] == "image_url"

    def test_video_url_format_does_not_change_image(self) -> None:
        msg = UserPromptMessage(content=[_image_part()])
        result = _convert(msg, credentials={"video_transfer_format": "video_url"})
        assert result["content"][0]["type"] == "image_url"


class TestInputAudioFormat:
    """When ``audio_transfer_format=input_audio``, AUDIO content is
    sent as an ``input_audio`` part with the data URL and a format
    hint. This is the shape OpenAI's native audio input spec uses.
    """

    def test_audio_uses_input_audio_part(self) -> None:
        msg = UserPromptMessage(content=[_audio_part()])
        result = _convert(msg, credentials={"audio_transfer_format": "input_audio"})
        assert result["content"] == [
            {
                "type": "input_audio",
                "input_audio": {
                    "data": AUDIO_DATA_URL,
                    "format": "wav",
                },
            }
        ]

    def test_input_audio_format_does_not_change_video(self) -> None:
        msg = UserPromptMessage(content=[_video_part()])
        result = _convert(msg, credentials={"audio_transfer_format": "input_audio"})
        assert result["content"][0]["type"] == "image_url"

    def test_input_audio_format_does_not_change_image(self) -> None:
        msg = UserPromptMessage(content=[_image_part()])
        result = _convert(msg, credentials={"audio_transfer_format": "input_audio"})
        assert result["content"][0]["type"] == "image_url"


# ---------------------------------------------------------------------------
# Mixed content
# ---------------------------------------------------------------------------


class TestMixedContent:
    """A user message can contain a mix of TEXT + IMAGE + VIDEO + AUDIO
    parts. The new credentials must affect only the modality they
    target.
    """

    def test_text_image_video_audio_with_all_new_formats(self) -> None:
        msg = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="describe this"),
                _image_part(),
                _video_part(),
                _audio_part(),
            ]
        )
        result = _convert(
            msg,
            credentials={
                "video_transfer_format": "video_url",
                "audio_transfer_format": "input_audio",
            },
        )
        assert result["content"] == [
            {"type": "text", "text": "describe this"},
            {
                "type": "image_url",
                "image_url": {"url": IMAGE_DATA_URL, "detail": "high"},
            },
            {"type": "video_url", "video_url": {"url": VIDEO_DATA_URL}},
            {
                "type": "input_audio",
                "input_audio": {
                    "data": AUDIO_DATA_URL,
                    "format": "wav",
                },
            },
        ]

    def test_text_only_message_unaffected(self) -> None:
        """A message with only TEXT content must not gain new parts."""
        msg = UserPromptMessage(content=[TextPromptMessageContent(data="just text")])
        result = _convert(
            msg,
            credentials={
                "video_transfer_format": "video_url",
                "audio_transfer_format": "input_audio",
            },
        )
        assert result["content"] == [{"type": "text", "text": "just text"}]
