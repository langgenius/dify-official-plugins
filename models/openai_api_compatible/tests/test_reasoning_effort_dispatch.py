"""Regression tests for ``reasoning_effort`` dispatch in OpenAILargeLanguageModel._invoke.

The Chat Completions path of the OpenAI-API-compatible provider used to pop
``reasoning_effort`` unconditionally and only re-add it when thinking mode
was explicitly turned on (``enable_thinking_value is True``). That meant a
user who left the thinking-mode toggle at its default under
``agent_thought_support: supported`` (the most common setup for OpenAI
reasoning models accessed through a gateway) had their
``reasoning_effort`` value silently discarded.

The Responses API path (added in 0.0.64) forwarded ``reasoning_effort``
without a thinking-mode gate, so the same parameter behaved differently
depending only on ``api_type``.

The fix changes the gate from ``enable_thinking_value is True`` to
``enable_thinking_value is not False`` so the top-level
``reasoning_effort`` flows through when thinking mode is at its default
(``None``), while still suppressing it for users who explicitly disable
thinking mode. The ``chat_template_kwargs`` mirror stays gated on
extended compatibility mode (since llama.cpp etc. consume that and
strict OpenAI mode does not).

See https://github.com/langgenius/dify-official-plugins/issues/3827.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import OpenAILargeLanguageModel

SUPER_INVOKE = (
    "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke"
)


def _prompt_messages():
    return [UserPromptMessage(content="ping")]


def _capture_invoke(credentials, model_parameters, model="gpt-5.6-luna"):
    """Run ``_invoke`` with the base implementation stubbed out and return ``model_parameters``.

    The base OAICompat supercall is mocked to capture the post-dispatch
    ``model_parameters`` dict without making a real network request.
    """
    llm = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["model_parameters"] = dict(model_parameters)
        # Non-streaming: the caller post-processes an LLMResult, so return a stand-in.
        return MagicMock()

    with patch(SUPER_INVOKE, new=fake_super):
        llm._invoke(
            model=model,
            credentials=credentials,
            prompt_messages=_prompt_messages(),
            model_parameters=dict(model_parameters),
            stream=False,
        )

    return captured["model_parameters"]


# ---------------------------------------------------------------------------
# Top-level `reasoning_effort` propagation
# ---------------------------------------------------------------------------


def test_thinking_untouched_and_supported_forwards_reasoning_effort():
    """The bug: default-None thinking mode silently dropped ``reasoning_effort``."""
    params = _capture_invoke(
        credentials={"mode": "chat", "agent_thought_support": "supported"},
        model_parameters={"reasoning_effort": "high"},
    )
    assert params.get("reasoning_effort") == "high"


def test_thinking_explicitly_enabled_forwards_reasoning_effort():
    """Pre-fix behaviour for this case was correct; ensure the fix preserves it."""
    params = _capture_invoke(
        credentials={"mode": "chat", "agent_thought_support": "supported"},
        model_parameters={"enable_thinking": True, "reasoning_effort": "high"},
    )
    assert params.get("reasoning_effort") == "high"


def test_thinking_explicitly_disabled_suppresses_reasoning_effort():
    """New behaviour: explicit ``enable_thinking=False`` still suppresses the param."""
    params = _capture_invoke(
        credentials={"mode": "chat", "agent_thought_support": "supported"},
        model_parameters={"enable_thinking": False, "reasoning_effort": "high"},
    )
    assert "reasoning_effort" not in params


def test_only_thinking_supported_forwards_reasoning_effort():
    """``agent_thought_support: only_thinking_supported`` forces thinking on, so propagate."""
    params = _capture_invoke(
        credentials={"mode": "chat", "agent_thought_support": "only_thinking_supported"},
        model_parameters={"reasoning_effort": "medium"},
    )
    assert params.get("reasoning_effort") == "medium"


def test_not_supported_suppresses_reasoning_effort():
    """``agent_thought_support: not_supported`` forces thinking off, so suppress."""
    params = _capture_invoke(
        credentials={"mode": "chat", "agent_thought_support": "not_supported"},
        model_parameters={"reasoning_effort": "high"},
    )
    assert "reasoning_effort" not in params


def test_reasoning_effort_absent_when_not_set():
    """Sanity check: when the user never sets ``reasoning_effort``, it stays absent."""
    params = _capture_invoke(
        credentials={"mode": "chat", "agent_thought_support": "supported"},
        model_parameters={"max_tokens": 128},
    )
    assert "reasoning_effort" not in params


# ---------------------------------------------------------------------------
# `chat_template_kwargs` mirror behaviour
# ---------------------------------------------------------------------------


def test_strict_compatibility_mode_does_not_mirror_to_chat_template_kwargs():
    """Strict OpenAI mode: top-level only, no ``chat_template_kwargs`` mirror."""
    params = _capture_invoke(
        credentials={
            "mode": "chat",
            "agent_thought_support": "supported",
            "compatibility_mode": "strict",
        },
        model_parameters={"reasoning_effort": "high"},
    )
    assert params.get("reasoning_effort") == "high"
    assert "chat_template_kwargs" not in params


def test_extended_compatibility_mode_mirrors_to_chat_template_kwargs():
    """Extended mode: top-level + ``chat_template_kwargs`` for llama.cpp / vLLM."""
    params = _capture_invoke(
        credentials={
            "mode": "chat",
            "agent_thought_support": "supported",
            "compatibility_mode": "extended",
        },
        model_parameters={"reasoning_effort": "high"},
    )
    assert params.get("reasoning_effort") == "high"
    assert params.get("chat_template_kwargs", {}).get("reasoning_effort") == "high"


def test_extended_mode_suppresses_reasoning_effort_in_chat_template_kwargs_when_thinking_disabled():
    """Extended mode + explicit ``enable_thinking=False``: top-level suppresses,
    and the ``reasoning_effort`` entry does NOT leak into ``chat_template_kwargs``.

    Note: ``chat_template_kwargs`` itself may still be populated with the
    ``enable_thinking`` and ``thinking`` entries (see line 603:
    ``enable_thinking_value is not None and strict_compatibility_value
    is False``); the assertion here is that the ``reasoning_effort`` entry
    does NOT leak into that dict.
    """
    params = _capture_invoke(
        credentials={
            "mode": "chat",
            "agent_thought_support": "supported",
            "compatibility_mode": "extended",
        },
        model_parameters={"enable_thinking": False, "reasoning_effort": "high"},
    )
    assert "reasoning_effort" not in params
    # The chat_template_kwargs dict (if populated) must not contain reasoning_effort.
    assert "reasoning_effort" not in params.get("chat_template_kwargs", {})


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------


def test_gate_is_not_false_not_is_true():
    """The fix must change ``is True`` to ``is not False`` on the
    ``enable_thinking_value`` half of the gate.

    Pre-fix the gate was ``if enable_thinking_value is True and
    reasoning_effort_value is not None``. The fix is ``if
    reasoning_effort_value is not None and enable_thinking_value is not
    False`` so the parameter flows through when thinking mode is at its
    default (None) under ``agent_thought_support: supported``.

    This guards against a future contributor reverting the gate back to
    ``is True``, which would silently re-introduce the bug.
    """
    import re
    from pathlib import Path

    llm_path = Path(__file__).resolve().parents[1] / "models" / "llm" / "llm.py"
    text = llm_path.read_text(encoding="utf-8")
    # Locate the gate immediately after the `reasoning_effort_value =
    # model_parameters.pop(...)` line. We look for the `and
    # enable_thinking_value is not False` clause.
    assert "enable_thinking_value is not False" in text, (
        "expected 'enable_thinking_value is not False' in the reasoning_effort "
        "gate; the fix appears to have been reverted"
    )
    # Negative check: the old buggy form must be gone.
    assert re.search(
        r"if\s+enable_thinking_value\s+is\s+True\s+and\s+reasoning_effort_value",
        text,
    ) is None, (
        "the buggy 'enable_thinking_value is True and reasoning_effort_value' "
        "gate has been re-introduced"
    )