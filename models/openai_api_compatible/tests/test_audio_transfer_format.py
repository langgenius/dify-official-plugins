"""Regression tests for ``audio_transfer_format`` in OpenAILargeLanguageModel.

The OpenAI-API-compatible plugin previously hardcoded AUDIO content parts to
the ``image_url`` shape, regardless of the upstream provider's wire format.
OpenAI multimodal endpoints that accept the ``input_audio`` content part
(introduced with gpt-4o-audio-preview) reject the request because the data
URI is decoded as an image rather than an audio payload.

This fix adds an ``audio_transfer_format`` model credential with two options:
- ``image_url_data_uri`` (default): preserves the pre-existing behaviour.
  LiteLLM dispatches this into Vertex Gemini's ``inline_data``.
- ``input_audio``: the OpenAI multimodal shape, with ``input_audio.data``
  carrying the raw base64 and ``input_audio.format`` carrying the audio
  format (e.g. ``wav`` / ``mp3``).

See the symmetric ``video_transfer_format`` fix in PR #4001 for the
parallel VIDEO branch; this PR closes out the AUDIO branch.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from dify_plugin.entities.model.message import (
    AudioPromptMessageContent,
    UserPromptMessage,
)

from models.llm.llm import OpenAILargeLanguageModel

# Raw base64 placeholder ("AAAA" decodes to 3 zero bytes); the value is
# irrelevant for these tests — only the wire format matters.
_AUDIO_BASE64 = "AAAA"
_AUDIO_DATA_URI = "data:audio/wav;base64,AAAA"


def _audio_user_message() -> UserPromptMessage:
    return UserPromptMessage(
        content=[
            AudioPromptMessageContent(
                mime_type="audio/wav",
                base64_data=_AUDIO_BASE64,
                format="wav",
            )
        ]
    )


def _convert(credentials):
    """Run ``_convert_prompt_message_to_dict`` and return the single content part."""
    llm = OpenAILargeLanguageModel(model_schemas=[])
    message = _audio_user_message()
    result = llm._convert_prompt_message_to_dict(message, credentials=credentials)
    assert result["role"] == "user"
    assert isinstance(result["content"], list)
    assert len(result["content"]) == 1
    return result["content"][0]


# ---------------------------------------------------------------------------
# Default behaviour preserved (backward compatibility)
# ---------------------------------------------------------------------------


def test_default_uses_image_url_data_uri():
    """No credential set: legacy behaviour, audio on ``image_url`` part."""
    part = _convert(credentials=None)
    assert part == {
        "type": "image_url",
        "image_url": {"url": _AUDIO_DATA_URI},
    }


def test_default_explicit_image_url_data_uri():
    """``image_url_data_uri`` explicitly: same as default."""
    part = _convert(credentials={"audio_transfer_format": "image_url_data_uri"})
    assert part == {
        "type": "image_url",
        "image_url": {"url": _AUDIO_DATA_URI},
    }


def test_empty_string_treated_as_default():
    """Empty-string credential value: fall back to the legacy behaviour."""
    part = _convert(credentials={"audio_transfer_format": ""})
    assert part["type"] == "image_url"
    assert part["image_url"]["url"] == _AUDIO_DATA_URI


# ---------------------------------------------------------------------------
# New option: input_audio
# ---------------------------------------------------------------------------


def test_input_audio_format_emits_input_audio_part():
    """``input_audio``: raw base64 on ``input_audio.data``, format on ``input_audio.format``."""
    part = _convert(credentials={"audio_transfer_format": "input_audio"})
    assert part == {
        "type": "input_audio",
        "input_audio": {
            "data": _AUDIO_BASE64,
            "format": "wav",
        },
    }


def test_input_audio_data_strips_data_uri_prefix():
    """``input_audio.data`` must NOT carry the ``data:audio/wav;base64,`` prefix."""
    part = _convert(credentials={"audio_transfer_format": "input_audio"})
    assert "data:" not in part["input_audio"]["data"]


def test_input_audio_data_passes_raw_base64_unchanged():
    """``input_audio.data`` is the raw base64 from the source content object."""
    part = _convert(credentials={"audio_transfer_format": "input_audio"})
    assert part["input_audio"]["data"] == _AUDIO_BASE64


def test_input_audio_format_carries_format_string():
    """``input_audio.format`` mirrors the source content's ``format`` field (e.g. ``wav``)."""
    part = _convert(credentials={"audio_transfer_format": "input_audio"})
    assert part["input_audio"]["format"] == "wav"


def test_input_audio_does_not_emit_image_url_part():
    """``input_audio`` must NOT also emit an ``image_url`` part (no double-send)."""
    part = _convert(credentials={"audio_transfer_format": "input_audio"})
    assert "image_url" not in part


def test_image_url_data_uri_does_not_emit_input_audio_part():
    """``image_url_data_uri`` must NOT emit an ``input_audio`` part."""
    part = _convert(credentials={"audio_transfer_format": "image_url_data_uri"})
    assert "input_audio" not in part


# ---------------------------------------------------------------------------
# Unknown credential values
# ---------------------------------------------------------------------------


def test_unknown_value_falls_back_to_legacy():
    """Unknown credential value: fall back to the legacy ``image_url`` behaviour.

    This matches the broader pattern in the plugin where unknown enum values
    are treated as the default rather than raising — keeps existing
    configurations working even if the schema evolves.
    """
    part = _convert(credentials={"audio_transfer_format": "experimental_url"})
    assert part["type"] == "image_url"
    assert part["image_url"]["url"] == _AUDIO_DATA_URI


# ---------------------------------------------------------------------------
# Provider-yaml schema
# ---------------------------------------------------------------------------


def test_provider_yaml_exposes_audio_transfer_format():
    """``audio_transfer_format`` must appear in the model credential schema."""
    yaml_path = (
        Path(__file__).resolve().parents[1] / "provider" / "openai_api_compatible.yaml"
    )
    parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    model_schema = parsed["model_credential_schema"]["credential_form_schemas"]
    schema = next(
        (s for s in model_schema if s.get("variable") == "audio_transfer_format"),
        None,
    )
    assert schema is not None, (
        "audio_transfer_format credential must appear in model_credential_schema"
    )
    # Scoped to LLM only via show_on.
    assert schema["show_on"] == [{"variable": "__model_type", "value": "llm"}]
    # Default is image_url_data_uri (opt-out, preserves legacy behaviour).
    assert schema["default"] == "image_url_data_uri"
    # Both options present.
    option_values = {opt["value"] for opt in schema["options"]}
    assert option_values == {"image_url_data_uri", "input_audio"}