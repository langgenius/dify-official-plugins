"""Regression tests for ``video_transfer_format`` in OpenAILargeLanguageModel.

The OpenAI-API-compatible plugin previously hardcoded VIDEO content parts to
the ``image_url`` shape, regardless of the upstream provider's wire format.
OpenAI-compatible servers that implement the multimodal ``video_url`` content
part (e.g. vLLM, directly or behind a LiteLLM proxy) reject the request with
HTTP 400 because the ``image_url`` payload is decoded as an image.

This fix adds a ``video_transfer_format`` model credential with two options:
- ``image_url_data_uri`` (default): preserves the pre-existing behaviour.
  LiteLLM dispatches this into Vertex Gemini's ``inline_data``.
- ``video_url``: the OpenAI multimodal shape, the one OpenAI-compatible
  servers that define a ``video_url`` content part expect.

See https://github.com/langgenius/dify-official-plugins/issues/3696.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from dify_plugin.entities.model.message import (
    UserPromptMessage,
    VideoPromptMessageContent,
)

from models.llm.llm import OpenAILargeLanguageModel

# A short base64 placeholder ("AAAA" decodes to 3 zero bytes); the value is
# irrelevant for these tests — only the wire format matters.
_VIDEO_DATA_URI = "data:video/mp4;base64,AAAA"


def _video_user_message() -> UserPromptMessage:
    return UserPromptMessage(
        content=[
            VideoPromptMessageContent(
                mime_type="video/mp4",
                base64_data="AAAA",
                format="mp4",
            )
        ]
    )


def _convert(credentials):
    """Run ``_convert_prompt_message_to_dict`` and return the single content part."""
    llm = OpenAILargeMessageModel_safe()
    message = _video_user_message()
    result = llm._convert_prompt_message_to_dict(message, credentials=credentials)
    assert result["role"] == "user"
    assert isinstance(result["content"], list)
    assert len(result["content"]) == 1
    return result["content"][0]


def OpenAILargeMessageModel_safe():
    return OpenAILargeLanguageModel(model_schemas=[])


# ---------------------------------------------------------------------------
# Default behaviour preserved (backward compatibility)
# ---------------------------------------------------------------------------


def test_default_uses_image_url_data_uri():
    """No credential set: legacy behaviour, video on ``image_url`` part."""
    part = _convert(credentials=None)
    assert part == {
        "type": "image_url",
        "image_url": {"url": _VIDEO_DATA_URI},
    }


def test_default_explicit_image_url_data_uri():
    """``image_url_data_uri`` explicitly: same as default."""
    part = _convert(credentials={"video_transfer_format": "image_url_data_uri"})
    assert part == {
        "type": "image_url",
        "image_url": {"url": _VIDEO_DATA_URI},
    }


def test_empty_string_treated_as_default():
    """Empty-string credential value: fall back to the legacy behaviour."""
    part = _convert(credentials={"video_transfer_format": ""})
    assert part["type"] == "image_url"
    assert part["image_url"]["url"] == _VIDEO_DATA_URI


# ---------------------------------------------------------------------------
# New option: video_url
# ---------------------------------------------------------------------------


def test_video_url_format_emits_video_url_part():
    """``video_url``: video on the OpenAI multimodal ``video_url`` part."""
    part = _convert(credentials={"video_transfer_format": "video_url"})
    assert part == {
        "type": "video_url",
        "video_url": {"url": _VIDEO_DATA_URI},
    }


def test_video_url_does_not_emit_image_url_part():
    """``video_url`` must NOT also emit an ``image_url`` part (no double-send)."""
    part = _convert(credentials={"video_transfer_format": "video_url"})
    assert "image_url" not in part


def test_image_url_data_uri_does_not_emit_video_url_part():
    """``image_url_data_uri`` must NOT emit a ``video_url`` part."""
    part = _convert(credentials={"video_transfer_format": "image_url_data_uri"})
    assert "video_url" not in part


# ---------------------------------------------------------------------------
# Unknown credential values
# ---------------------------------------------------------------------------


def test_unknown_value_falls_back_to_legacy():
    """Unknown credential value: fall back to the legacy ``image_url`` behaviour.

    This matches the broader pattern in the plugin where unknown enum values
    are treated as the default rather than raising — keeps existing
    configurations working even if the schema evolves.
    """
    part = _convert(credentials={"video_transfer_format": "experimental_url"})
    assert part["type"] == "image_url"
    assert part["image_url"]["url"] == _VIDEO_DATA_URI


# ---------------------------------------------------------------------------
# Provider-yaml schema
# ---------------------------------------------------------------------------


def test_provider_yaml_exposes_video_transfer_format():
    """``video_transfer_format`` must appear in the model credential schema."""
    yaml_path = (
        Path(__file__).resolve().parents[1] / "provider" / "openai_api_compatible.yaml"
    )
    parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    model_schema = parsed["model_credential_schema"]["credential_form_schemas"]
    schema = next(
        (s for s in model_schema if s.get("variable") == "video_transfer_format"),
        None,
    )
    assert schema is not None, (
        "video_transfer_format credential must appear in model_credential_schema"
    )
    # Scoped to LLM only via show_on.
    assert schema["show_on"] == [{"variable": "__model_type", "value": "llm"}]
    # Default is image_url_data_uri (opt-out, preserves legacy behaviour).
    assert schema["default"] == "image_url_data_uri"
    # Both options present.
    option_values = {opt["value"] for opt in schema["options"]}
    assert option_values == {"image_url_data_uri", "video_url"}