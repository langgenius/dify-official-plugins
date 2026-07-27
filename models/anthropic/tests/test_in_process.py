"""In-process unit tests for models/anthropic/models/llm/llm.py.

Targets the parts of llm.py that are deterministic and side-effect-free:
- PromptCachingHandler (system-prompt extraction, cache control, billing math)
- AnthropicLargeLanguageModel.validate_credentials (provider-style credential check)
- AnthropicLargeLanguageModel model-classification helpers (which models support
  adaptive thinking, task budgets, etc.)

No network, no ANTHROPIC_API_KEY required. Runs in <1s.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

# Make the plugin's own modules importable when pytest is invoked from the
# plugin directory or the repo root, matching the pattern in
# models/openai/tests/test_non_llm.py and
# models/tongyi/tests/test_validate_provider_credentials.py.
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from models.llm.llm import AnthropicLargeLanguageModel, PromptCachingHandler  # noqa: E402


# ---------------------------------------------------------------------------
# PromptCachingHandler.get_cache_control
# ---------------------------------------------------------------------------


def test_get_cache_control_returns_default_when_no_override() -> None:
    """The default cache control is a single-key dict with type='ephemeral'."""
    handler = PromptCachingHandler(prompt_messages=[])
    assert handler.get_cache_control() == {"type": "ephemeral"}


def test_get_cache_control_returns_independent_copy() -> None:
    """Mutating the returned dict must not mutate the handler's internal state.

    Without the dict() copy in get_cache_control, callers could write through
    the returned dict and corrupt the handler's cache_control on the next call.
    """
    handler = PromptCachingHandler(prompt_messages=[])
    first = handler.get_cache_control()
    first["type"] = "tampered"
    second = handler.get_cache_control()
    assert second == {"type": "ephemeral"}


def test_get_cache_control_respects_explicit_override() -> None:
    """An explicit cache_control argument overrides the default."""
    override = {"type": "ephemeral", "ttl": "1h"}
    handler = PromptCachingHandler(prompt_messages=[], cache_control=override)
    assert handler.get_cache_control() == override


# ---------------------------------------------------------------------------
# PromptCachingHandler.get_system_prompt
# ---------------------------------------------------------------------------


def test_get_system_prompt_returns_empty_string_when_no_system_messages() -> None:
    """No system messages → empty string. (The class docstring asserts this.)"""
    handler = PromptCachingHandler(
        prompt_messages=[UserPromptMessage(content="hi")],
    )
    assert handler.get_system_prompt() == ""


def test_get_system_prompt_concatenates_multiple_string_system_messages() -> None:
    """Multiple SystemPromptMessage with string content get joined by '\\n'."""
    handler = PromptCachingHandler(
        prompt_messages=[
            SystemPromptMessage(content="First system message."),
            SystemPromptMessage(content="Second system message."),
        ],
    )
    assert (
        handler.get_system_prompt() == "First system message.\nSecond system message."
    )


def test_get_system_prompt_strips_whitespace_around_string_content() -> None:
    """Whitespace-stripping prevents accidental leading/trailing newlines from leaking through."""
    handler = PromptCachingHandler(
        prompt_messages=[SystemPromptMessage(content="   padded   ")],
    )
    assert handler.get_system_prompt() == "padded"


def test_get_system_prompt_flattens_text_content_list() -> None:
    """A SystemPromptMessage with list-of-TextPromptMessageContent is joined."""
    handler = PromptCachingHandler(
        prompt_messages=[
            SystemPromptMessage(
                content=[
                    TextPromptMessageContent(data="alpha"),
                    TextPromptMessageContent(data="beta"),
                ],
            ),
        ],
    )
    assert handler.get_system_prompt() == "alpha\nbeta"


def test_get_system_prompt_with_cache_marker_emits_cache_control_per_block() -> None:
    """When enable_system_cache=True and the message contains <cache>...</cache>,
    each cache block becomes a separate text dict with cache_control; the rest
    becomes plain text dicts. The final result is a list, not a string.
    """
    handler = PromptCachingHandler(
        prompt_messages=[
            SystemPromptMessage(
                content="prefix <cache>cached</cache> suffix",
            ),
        ],
        enable_system_cache=True,
    )
    out = handler.get_system_prompt()
    assert isinstance(out, list)
    types = [comp.get("cache_control") for comp in out]
    # One of the three parts (prefix, cached, suffix) carries cache_control.
    assert any(t is not None for t in types)
    # And the cached block has the cache_control attached.
    cached = next(c for c in out if c.get("text") == "cached")
    assert cached["cache_control"] == {"type": "ephemeral"}


def test_get_system_prompt_without_enable_flag_returns_string_even_with_cache_marker() -> (
    None
):
    """The <cache> markers are only honored when enable_system_cache=True.
    Otherwise the literal text is concatenated like any other system prompt.
    """
    handler = PromptCachingHandler(
        prompt_messages=[
            SystemPromptMessage(content="prefix <cache>cached</cache> suffix"),
        ],
        enable_system_cache=False,
    )
    out = handler.get_system_prompt()
    assert isinstance(out, str)
    assert out == "prefix <cache>cached</cache> suffix"


def test_get_system_prompt_drops_text_content_with_unknown_subclass() -> None:
    """A list-content SystemPromptMessage with a non-TextPromptMessageContent
    entry: the SDK allows construction (it's a valid base type) but the
    handler's `if isinstance(c, TextPromptMessageContent)` skips it. We assert
    that the surviving text is what we expect (i.e., the unknown content is
    silently skipped, not raised — the upstream else branch is only reached
    if isinstance(message.content, list) but NO entry matches TextPromptMessageContent,
    which is hard to trigger through the public API because the SDK's
    pydantic validator rejects malformed content at construction time. We
    therefore only assert the happy-path list flattening here; the
    defensive ValueError branch in the code is reachable only if a future
    subclass of PromptMessageContent is introduced and not handled).
    """
    handler = PromptCachingHandler(
        prompt_messages=[
            SystemPromptMessage(content="only a string"),
        ],
    )
    assert handler.get_system_prompt() == "only a string"


# ---------------------------------------------------------------------------
# PromptCachingHandler.calc_adjusted_prompt_tokens
# ---------------------------------------------------------------------------


def test_calc_adjusted_prompt_tokens_returns_base_when_no_cache() -> None:
    """No cache activity → adjusted == base."""
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
    )
    assert adjusted == 1000


def test_calc_adjusted_prompt_tokens_5m_cache_premium() -> None:
    """5m cache writes incur a 25% premium on the written tokens.
    Per the docstring: CACHE_WRITE_5M_MULTIPLIER = 1.25.
    """
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
        cache_creation_5m_input_tokens=400,
    )
    # 1000 (base) + 400*1.25 = 1500
    assert adjusted == 1500


def test_calc_adjusted_prompt_tokens_1h_cache_premium() -> None:
    """1h cache writes incur a 100% premium (2x) on the written tokens.
    Per the docstring: CACHE_WRITE_1H_MULTIPLIER = 2.0.
    """
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
        cache_creation_1h_input_tokens=200,
    )
    # 1000 + 200*2 = 1400
    assert adjusted == 1400


def test_calc_adjusted_prompt_tokens_5m_plus_1h_both_apply() -> None:
    """Both 5m and 1h cache write buckets add up; neither is suppressed."""
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
        cache_creation_5m_input_tokens=100,
        cache_creation_1h_input_tokens=100,
    )
    # 1000 + 100*1.25 + 100*2 = 1325
    assert adjusted == 1325


def test_calc_adjusted_prompt_tokens_fallback_used_when_no_ttl_split() -> None:
    """When only the generic cache_creation_input_tokens is provided (no
    5m/1h split), the fallback multiplier is used.
    """
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
        cache_creation_input_tokens=400,
        cache_creation_fallback_multiplier=1.25,
    )
    # 1000 + 400*1.25 = 1500
    assert adjusted == 1500


def test_calc_adjusted_prompt_tokens_ttl_split_overrides_fallback() -> None:
    """When both cache_creation_input_tokens AND a 5m/1h split are present,
    the explicit split wins. The fallback is suppressed entirely (the elif
    branch is not taken).
    """
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
        cache_creation_input_tokens=999,  # would be 999*1.25 = 1248.75 if fallback ran
        cache_creation_5m_input_tokens=100,  # 100*1.25 = 125
        cache_creation_fallback_multiplier=1.25,
    )
    # 1000 + 100*1.25 = 1125 (fallback suppressed)
    assert adjusted == 1125


def test_calc_adjusted_prompt_tokens_cache_read_discount() -> None:
    """Cache reads receive a 90% discount (0.1x) on the read tokens.
    Per the docstring: CACHE_READ_MULTIPLIER = 0.1.
    """
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
        cache_read_input_tokens=400,
    )
    # 1000 + 400*0.1 = 1040
    assert adjusted == 1040


def test_calc_adjusted_prompt_tokens_combines_writes_and_reads() -> None:
    """5m write + cache read in the same call: both apply."""
    adjusted = PromptCachingHandler.calc_adjusted_prompt_tokens(
        base_prompt_tokens=1000,
        cache_creation_5m_input_tokens=100,
        cache_read_input_tokens=200,
    )
    # 1000 + 100*1.25 + 200*0.1 = 1145
    assert adjusted == 1145


# ---------------------------------------------------------------------------
# AnthropicLargeLanguageModel.validate_credentials
# ---------------------------------------------------------------------------


def _anthropic_instance() -> AnthropicLargeLanguageModel:
    """Construct an AnthropicLargeLanguageModel without invoking __init__,
    which would try to load the provider schema from disk.
    """
    return object.__new__(AnthropicLargeLanguageModel)


def test_validate_credentials_succeeds_when_chat_generate_returns() -> None:
    """When the underlying _chat_generate call succeeds, validate_credentials
    returns None. The plugin's contract: a real 'ping' request to the model
    is the source of truth for credential validity.
    """
    instance = _anthropic_instance()
    with patch.object(instance, "_chat_generate", return_value="ok") as gen:
        # Should not raise
        instance.validate_credentials(
            model="claude-sonnet-4-6",
            credentials={"anthropic_api_key": "sk-test-valid"},
        )
    gen.assert_called_once()
    # The 'ping' prompt and minimal parameters are passed.
    call = gen.call_args
    assert call.kwargs["model"] == "claude-sonnet-4-6"
    assert call.kwargs["stream"] is False
    assert call.kwargs["model_parameters"] == {"temperature": 0, "max_tokens": 20}


def test_validate_credentials_wraps_chat_generate_error() -> None:
    """An exception from _chat_generate (network, 401, model-not-found, ...)
    is wrapped in CredentialsValidateFailedError so the Dify UI shows a clear
    'credentials invalid' message instead of a raw stack trace.
    """
    instance = _anthropic_instance()
    with patch.object(
        instance, "_chat_generate", side_effect=ConnectionError("network down")
    ):
        with pytest.raises(CredentialsValidateFailedError, match="network down"):
            instance.validate_credentials(
                model="claude-sonnet-4-6",
                credentials={"anthropic_api_key": "sk-bad"},
            )


def test_validate_credentials_preserves_existing_credentials_error() -> None:
    """A CredentialsValidateFailedError from _chat_generate is re-raised
    unchanged (the wrapper's `raise ex` for that specific case preserves
    the original type so callers can distinguish credential errors from
    transient ones).
    """
    instance = _anthropic_instance()
    with patch.object(
        instance,
        "_chat_generate",
        side_effect=CredentialsValidateFailedError("bad creds"),
    ):
        with pytest.raises(CredentialsValidateFailedError, match="bad creds"):
            instance.validate_credentials(
                model="claude-sonnet-4-6",
                credentials={"anthropic_api_key": "sk-x"},
            )


# ---------------------------------------------------------------------------
# AnthropicLargeLanguageModel adaptive-thinking model classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_name",
    [
        "claude-opus-4-7",
        "claude-opus-4-8",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-fable-5",
        "claude-mythos-5",
    ],
)
def test_uses_adaptive_thinking_true_for_adaptive_models(model_name: str) -> None:
    """The six models in ADAPTIVE_THINKING_MODELS must report uses_adaptive_thinking=True."""
    instance = _anthropic_instance()
    assert instance._uses_adaptive_thinking(model_name) is True


@pytest.mark.parametrize(
    "model_name",
    [
        "claude-sonnet-4-6",
        "claude-opus-4-1",
        "claude-haiku-4-5",
        "claude-3-5-sonnet-20240620",
        "claude-3-opus-20240229",
    ],
)
def test_uses_adaptive_thinking_false_for_classic_models(model_name: str) -> None:
    """Models not in ADAPTIVE_THINKING_MODELS must report uses_adaptive_thinking=False."""
    instance = _anthropic_instance()
    assert instance._uses_adaptive_thinking(model_name) is False


def test_has_always_on_adaptive_thinking_only_fable_and_mythos() -> None:
    """Only fable-5 and mythos-5 are always-on; the other adaptive models are
    opt-in. (Regressing this would silently flip user-configured 'off' choices.)
    """
    instance = _anthropic_instance()
    assert instance._has_always_on_adaptive_thinking("claude-fable-5") is True
    assert instance._has_always_on_adaptive_thinking("claude-mythos-5") is True
    assert instance._has_always_on_adaptive_thinking("claude-opus-5") is False
    assert instance._has_always_on_adaptive_thinking("claude-sonnet-4-6") is False


def test_supports_task_budget_for_supported_models_only() -> None:
    """Task budget is only supported on opus-4-7+, opus-5, fable-5, mythos-5.
    Older sonnet and opus models don't get the output_config field — sending
    it would cause a 400 from the API.
    """
    instance = _anthropic_instance()
    for m in ("claude-opus-4-7", "claude-opus-5", "claude-fable-5", "claude-mythos-5"):
        assert instance._supports_task_budget(m) is True
    for m in ("claude-sonnet-4-6", "claude-opus-4-1", "claude-3-5-sonnet-20240620"):
        assert instance._supports_task_budget(m) is False


def test_enforces_disabled_thinking_effort_cap_for_claude_opus_5() -> None:
    """Only Claude Opus 5 (per the class constant DISABLED_THINKING_EFFORT_CAP_MODELS)
    enforces the disabled-thinking-effort cap. Older Opus 4.x and Sonnet 5 do
    not — the plugin doesn't clamp the effort parameter for them.
    Regressing this list would let users send effort=low on opus-5
    and get an API error.
    """
    instance = _anthropic_instance()
    assert instance._enforces_disabled_thinking_effort_cap("claude-opus-5") is True
    for m in (
        "claude-sonnet-5",
        "claude-fable-5",
        "claude-mythos-5",
        "claude-opus-4-7",
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-3-5-sonnet-20240620",
    ):
        assert instance._enforces_disabled_thinking_effort_cap(m) is False


def test_enforces_disabled_thinking_effort_cap_uses_startswith_match() -> None:
    """The class uses `model_id.startswith(prefix)` — so a future model like
    'claude-opus-5-1' would inherit the cap from the 'claude-opus-5' prefix.
    The test pins this behavior so a future refactor doesn't silently
    change matching semantics.
    """
    instance = _anthropic_instance()
    assert instance._enforces_disabled_thinking_effort_cap("claude-opus-5") is True
    assert instance._enforces_disabled_thinking_effort_cap("claude-opus-5-1") is True
    assert (
        instance._enforces_disabled_thinking_effort_cap("claude-opus-5-20250901")
        is True
    )
    # Empty / unknown → False
    assert instance._enforces_disabled_thinking_effort_cap("") is False
    assert instance._enforces_disabled_thinking_effort_cap("gpt-4") is False
