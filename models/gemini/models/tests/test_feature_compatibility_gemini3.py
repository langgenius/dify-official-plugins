"""Unit tests for the Gemini 3+ json_schema + tools compatibility layer (issue #3426).

The plugin's ``_validate_feature_compatibility`` historically hard-rejected
the combination of Structured Outputs (``json_schema``) with any built-in
tool (``grounding``, ``url_context``) on every model. On Gemini 3+ the
underlying Google API actually supports that combination — but only via
the Interactions API, not the legacy ``generate_content`` path. These
tests cover the model-detection helper and the validator's model-aware
relaxation of Rule 1.
"""

import pytest
from dify_plugin.errors.model import InvokeError

from models.llm.llm import GoogleLargeLanguageModel


# --- _is_gemini3_plus --------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "gemini-3.5-flash",
        "gemini-3-pro",
        "gemini-3.5-flash-preview",
        "gemini-3-flash",
        "GEMINI-3-pro",  # case-insensitive
        "gemini-3/",
        "gemini-3",
    ],
)
def test_is_gemini3_plus_true_for_gen_3_models(model: str) -> None:
    assert GoogleLargeLanguageModel._is_gemini3_plus(model) is True


@pytest.mark.parametrize(
    "model",
    [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-image",
        # Must not over-match: "gemini-3" without a separator is treated as
        # 3+ (covered above), but other Gemini families with "3" later in
        # the name and no separator ("gemini-30", "gemini-3abc") must not.
        "gemini-30-flash",
        "gemini-3abc",
        # Non-Gemini families must not match.
        "claude-3-sonnet",
    ],
)
def test_is_gemini3_plus_false_for_non_gen_3_models(model: str) -> None:
    assert GoogleLargeLanguageModel._is_gemini3_plus(model) is False


@pytest.mark.parametrize("model", ["", None, "  ", "gemini", "claude-3-opus"])
def test_is_gemini3_plus_handles_empty_and_unknown(model) -> None:
    """Empty / unknown model names must not raise; they default to non-3+."""
    assert GoogleLargeLanguageModel._is_gemini3_plus(model) is False


# --- _validate_feature_compatibility -----------------------------------------


def test_validator_relaxes_rule1_for_gemini3_json_schema_with_grounding() -> None:
    """Issue #3426: on Gemini 3+ the combination is supported (Interactions API)."""
    adjusted = GoogleLargeLanguageModel._validate_feature_compatibility(
        model_parameters={"json_schema": True, "grounding": True},
        tools=None,
        model="gemini-3.5-flash",
    )
    # Adjustments should be a no-op (the validator does not mutate
    # feature flags; it only suppresses the exception).
    assert adjusted == {"json_schema": True, "grounding": True}


def test_validator_relaxes_rule1_for_gemini3_json_schema_with_url_context() -> None:
    adjusted = GoogleLargeLanguageModel._validate_feature_compatibility(
        model_parameters={"json_schema": True, "url_context": True},
        tools=None,
        model="gemini-3-pro",
    )
    assert adjusted == {"json_schema": True, "url_context": True}


def test_validator_relaxes_rule1_for_gemini3_json_schema_with_both_tools() -> None:
    adjusted = GoogleLargeLanguageModel._validate_feature_compatibility(
        model_parameters={"json_schema": True, "grounding": True, "url_context": True},
        tools=None,
        model="gemini-3",
    )
    assert adjusted == {"json_schema": True, "grounding": True, "url_context": True}


def test_validator_still_raises_rule1_for_gemini25_json_schema_with_grounding() -> None:
    """Issue #3426: Gemini <= 2.5 must keep the strict enforcement (HTTP 400)."""
    with pytest.raises(InvokeError, match="json_schema"):
        GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"json_schema": True, "grounding": True},
            tools=None,
            model="gemini-2.5-flash",
        )


def test_validator_still_raises_rule1_for_gemini25_json_schema_with_url_context() -> None:
    with pytest.raises(InvokeError, match="json_schema"):
        GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"json_schema": True, "url_context": True},
            tools=None,
            model="gemini-2.0-flash",
        )


def test_validator_raises_rule1_when_model_is_unknown() -> None:
    """Without a model name we cannot prove Gemini 3+, so we must keep the
    strict Rule 1 (matches the prior behavior for unrecognized models)."""
    with pytest.raises(InvokeError, match="json_schema"):
        GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"json_schema": True, "grounding": True},
            tools=None,
            model=None,
        )


def test_validator_rule3_url_context_plus_code_execution_still_raises_for_gemini3() -> None:
    """Other rules (3: url_context + code_execution) stay strict on every model."""
    with pytest.raises(InvokeError, match="url_context"):
        GoogleLargeLanguageModel._validate_feature_compatibility(
            model_parameters={"url_context": True, "code_execution": True},
            tools=None,
            model="gemini-3.5-flash",
        )


def test_validator_rule5_tools_still_disables_grounding_on_gemini3() -> None:
    """Custom tools still force-disable grounding/url_context/code_execution
    even on Gemini 3+ (the function-calling conflict is real)."""

    class _FakeTool:
        pass

    tools = [_FakeTool()]
    adjusted = GoogleLargeLanguageModel._validate_feature_compatibility(
        model_parameters={"grounding": True, "url_context": True, "code_execution": True},
        tools=tools,
        model="gemini-3.5-flash",
    )
    assert adjusted == {
        "grounding": False,
        "url_context": False,
        "code_execution": False,
    }


def test_validator_passes_through_json_schema_alone() -> None:
    adjusted = GoogleLargeLanguageModel._validate_feature_compatibility(
        model_parameters={"json_schema": True},
        tools=None,
        model="gemini-2.5-flash",
    )
    assert adjusted == {"json_schema": True}


def test_validator_passes_through_grounding_alone() -> None:
    adjusted = GoogleLargeLanguageModel._validate_feature_compatibility(
        model_parameters={"grounding": True},
        tools=None,
        model="gemini-2.5-flash",
    )
    assert adjusted == {"grounding": True}


def test_validator_passes_through_empty() -> None:
    adjusted = GoogleLargeLanguageModel._validate_feature_compatibility(
        model_parameters={},
        tools=None,
        model="gemini-2.5-flash",
    )
    assert adjusted == {}


# --- module import smoke test -------------------------------------------------


def test_helpers_present_and_importable() -> None:
    """Sanity check that the static methods are present on the class."""
    assert hasattr(GoogleLargeLanguageModel, "_is_gemini3_plus")
    assert hasattr(GoogleLargeLanguageModel, "_validate_feature_compatibility")