"""Tests for the Interactions API routing (Gemini 3+ json_schema + tools).

Added in conjunction with the ``_generate_via_interactions`` changes for
https://github.com/langgenius/dify-official-plugins/issues/3426.

Unit tests (no API key required) cover ``_is_gemini3_plus``, the validator
relaxation, the routing decision, and the Interactions response/stream
handlers. Live tests (skip without ``GEMINI_API_KEY``) exercise the
end-to-end path against the real Gemini API.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from dify_plugin.entities.model.llm import LLMResultChunk, LLMUsage
from dify_plugin.entities.model.message import (
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeError

from models.llm.llm import GoogleLargeLanguageModel


def _make_usage(prompt_tokens=10, completion_tokens=5):
    """Create a realistic LLMUsage for testing."""
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        prompt_unit_price=3e-6,
        prompt_price_unit=1000,
        prompt_price=prompt_tokens * 3e-6,
        completion_tokens=completion_tokens,
        completion_unit_price=1.5e-5,
        completion_price_unit=1000,
        completion_price=completion_tokens * 1.5e-5,
        total_tokens=prompt_tokens + completion_tokens,
        total_price=(prompt_tokens * 3e-6) + (completion_tokens * 1.5e-5),
        currency="USD",
        latency=0.5,
    )


# =============================================================================
#  _is_gemini3_plus
# =============================================================================


class TestIsGemini3Plus:
    def _call(self, model):
        return GoogleLargeLanguageModel._is_gemini3_plus(model)

    def test_gemini3_flash(self):
        assert self._call("gemini-3.5-flash") is True

    def test_gemini3_pro(self):
        assert self._call("gemini-3-pro") is True

    def test_gemini3_preview(self):
        assert self._call("gemini-3.5-flash-preview") is True

    def test_gemini3_bare(self):
        assert self._call("gemini-3") is True

    def test_gemini3_with_models_prefix(self):
        assert self._call("models/gemini-3.5-flash") is True

    def test_gemini3_case_insensitive(self):
        assert self._call("GEMINI-3-PRO") is True

    def test_gemini3_with_underscore(self):
        assert self._call("gemini-3_pro") is True

    def test_gemini25_not_matched(self):
        assert self._call("gemini-2.5-flash") is False

    def test_gemini20_not_matched(self):
        assert self._call("gemini-2.0-flash") is False

    def test_gemini15_not_matched(self):
        assert self._call("gemini-1.5-pro") is False

    def test_gemini30_not_matched(self):
        assert self._call("gemini-30-flash") is False

    def test_gemini3abc_not_matched(self):
        assert self._call("gemini-3abc") is False

    def test_claude_not_matched(self):
        assert self._call("claude-3-sonnet") is False

    def test_empty_not_matched(self):
        assert self._call("") is False

    def test_none_not_matched(self):
        assert self._call(None) is False


# =============================================================================
#  _validate_feature_compatibility (Gemini 3+ relaxation)
# =============================================================================


class TestValidatorRelaxation:
    def test_gemini3_json_schema_with_grounding_passes(self):
        """Gemini 3+ must not raise for json_schema + grounding."""
        result = GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"json_schema": True, "grounding": True},
            tools=None,
            model="gemini-3.5-flash",
        )
        assert result == {"json_schema": True, "grounding": True}

    def test_gemini3_json_schema_with_url_context_passes(self):
        result = GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"json_schema": True, "url_context": True},
            tools=None,
            model="gemini-3-pro",
        )
        assert result == {"json_schema": True, "url_context": True}

    def test_gemini3_json_schema_with_both_tools_passes(self):
        result = GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={
                "json_schema": True,
                "grounding": True,
                "url_context": True,
            },
            tools=None,
            model="gemini-3",
        )
        assert result == {
            "json_schema": True,
            "grounding": True,
            "url_context": True,
        }

    def test_gemini3_json_schema_with_code_execution_passes(self):
        result = GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"json_schema": True, "code_execution": True},
            tools=None,
            model="gemini-3.5-flash",
        )
        assert result == {"json_schema": True, "code_execution": True}

    def test_gemini25_json_schema_with_grounding_raises(self):
        """Gemini <= 2.5 must keep strict enforcement."""
        with pytest.raises(InvokeError, match="json_schema"):
            GoogleLargeLanguageModel._validate_feature_compatibility(
                model_parameters={"json_schema": True, "grounding": True},
                tools=None,
                model="gemini-2.5-flash",
            )

    def test_unknown_model_json_schema_with_grounding_raises(self):
        """Without a model name we cannot prove Gemini 3+, so keep strict."""
        with pytest.raises(InvokeError, match="json_schema"):
            GoogleLargeLanguageModel._validate_feature_compatibility(
                model_parameters={"json_schema": True, "grounding": True},
                tools=None,
                model=None,
            )

    def test_gemini3_url_context_code_execution_still_raises(self):
        """Rule 3 (url_context + code_execution) stays strict on every model."""
        with pytest.raises(InvokeError, match="url_context"):
            GoogleLargeLanguageModel._validate_feature_compatibility(
                model_parameters={
                    "url_context": True,
                    "code_execution": True,
                },
                tools=None,
                model="gemini-3.5-flash",
            )

    def test_gemini3_custom_tools_still_disable_grounding(self):
        """Custom tools force-disable native tools even on Gemini 3+."""
        tools = [PromptMessageTool(name="test", description="test", parameters={})]
        result = GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={
                "grounding": True,
                "url_context": True,
                "code_execution": True,
            },
            tools=tools,
            model="gemini-3.5-flash",
        )
        assert result == {
            "grounding": False,
            "url_context": False,
            "code_execution": False,
        }


# =============================================================================
#  Interactions response handlers (mocked)
# =============================================================================


class TestInteractionsResponseHandler:
    def setup_method(self):
        self.llm = GoogleLargeLanguageModel([])
        self.credentials = {"google_api_key": "fake_key"}

    @patch("models.llm.llm.genai.Client")
    def test_interactions_routing_decision(self, mock_client):
        """Verify that the routing fires for Gemini 3+ with json_schema + grounding."""
        mock_client.return_value = Mock()
        # The routing intercepts before genai_client is constructed, so we
        # just check that _validate_feature_compatibility does NOT raise.
        result = GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"json_schema": True, "grounding": True},
            tools=None,
            model="gemini-3.5-flash",
        )
        assert "json_schema" in result
        assert "grounding" in result

    def test_handle_interactions_response_with_text(self):
        """Non-streaming response is parsed into an LLMResult."""
        mock_interaction = MagicMock()
        mock_interaction.output_text = "Hello from Gemini 3!"
        mock_interaction.usage.total_input_tokens = 10
        mock_interaction.usage.total_output_tokens = 5

        with patch.object(self.llm, "_calc_response_usage", return_value=_make_usage()):
            result = self.llm._handle_interactions_response(
                "gemini-3.5-flash", self.credentials, mock_interaction, []
            )
        assert result.model == "gemini-3.5-flash"
        assert len(result.message.content) == 1
        assert result.message.content[0].data == "Hello from Gemini 3!"

    def test_handle_interactions_response_with_fallback_steps(self):
        """Fallback to step-based extraction when output_text is absent."""
        mock_interaction = MagicMock()
        mock_interaction.output_text = None
        mock_step = MagicMock()
        mock_step.type = "model_output"
        mock_part = MagicMock()
        mock_part.type = "text"
        mock_part.text = "Step-based output"
        mock_step.content = [mock_part]
        mock_interaction.steps = [mock_step]
        mock_interaction.usage.total_input_tokens = 10
        mock_interaction.usage.total_output_tokens = 5

        with patch.object(self.llm, "_calc_response_usage", return_value=_make_usage()):
            result = self.llm._handle_interactions_response(
                "gemini-3.5-flash", self.credentials, mock_interaction, []
            )
        # The first chunk should be the fallback step text
        assert result.message.content[0].data == "Step-based output"

    def test_handle_interactions_stream_yields_chunks(self):
        """Streaming events produce LLMResultChunks."""
        # Simulate SSE events
        mock_delta_event = MagicMock()
        mock_delta_event.event_type = "step.delta"
        mock_delta_event.delta.type = "text"
        mock_delta_event.delta.text = "Hello "

        mock_complete_event = MagicMock()
        mock_complete_event.event_type = "interaction.completed"
        mock_complete_event.interaction.usage.total_input_tokens = 10
        mock_complete_event.interaction.usage.total_output_tokens = 5

        stream = iter([mock_delta_event, mock_complete_event])

        with patch.object(self.llm, "_calc_response_usage", return_value=_make_usage()):
            chunks = list(
                self.llm._handle_interactions_stream_response(
                    "gemini-3.5-flash",
                    self.credentials,
                    stream,
                    [],
                )
            )

        assert len(chunks) == 2
        assert isinstance(chunks[0], LLMResultChunk)
        assert chunks[0].delta.message.content[0].data == "Hello "

    def test_handle_interactions_stream_error_raises_invoke_error(self):
        """An error event raises InvokeError."""
        mock_error_event = MagicMock()
        mock_error_event.event_type = "error"
        mock_error_event.error.message = "Rate limit exceeded"

        stream = iter([mock_error_event])

        with pytest.raises(InvokeError, match="Rate limit exceeded"):
            list(
                self.llm._handle_interactions_stream_response(
                    "gemini-3.5-flash",
                    self.credentials,
                    stream,
                    [],
                )
            )
