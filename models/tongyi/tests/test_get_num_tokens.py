"""
Regression tests for TongyiLargeLanguageModel.get_num_tokens.

Historically get_num_tokens() short-circuited to 0 for every model because it
guarded on `get_customizable_model_schema(...) is not None`, and the Tongyi
override of that method *always* returns a schema. As a result the real
tokenizer never ran and Dify received 0 tokens for prompt trimming / max_tokens
budgeting on all Tongyi models.

These tests assert that:
  - Qwen-series models use the accurate local DashScope tokenizer.
  - Non-Qwen hosted models (kimi/glm/deepseek/...) and user-defined customizable
    models fall back to the offline gpt2 estimator instead of returning 0.
"""

import dify_plugin  # noqa: F401 - patches gevent before HTTP SDK imports
from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    UserPromptMessage,
)

from models.llm.llm import TongyiLargeLanguageModel


def _model() -> TongyiLargeLanguageModel:
    return TongyiLargeLanguageModel(model_schemas=[])


def _messages() -> list:
    return [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(
            content="Hello world, this is a reproduction test for get_num_tokens."
        ),
    ]


def test_qwen_model_returns_nonzero_tokens():
    """Built-in qwen models must run the real DashScope tokenizer."""
    num_tokens = _model().get_num_tokens("qwen-max", {}, _messages())
    assert num_tokens > 0


def test_qwen38_max_returns_nonzero_tokens():
    """The specific model from the bug report must not return 0."""
    num_tokens = _model().get_num_tokens("qwen3.8-max", {}, _messages())
    assert num_tokens > 0


def test_qwen_tokenizer_matches_dashscope_encoding():
    """qwen token count should equal the DashScope tokenizer's own encoding."""
    from dashscope import get_tokenizer

    prompt = _model()._convert_messages_to_prompt(_messages())
    expected = len(get_tokenizer("qwen-plus").encode(prompt))
    assert _model().get_num_tokens("qwen-plus", {}, _messages()) == expected
    assert expected > 0


def test_non_qwen_predefined_model_falls_back_to_gpt2():
    """Non-qwen hosted models are unsupported by DashScope's tokenizer and must
    fall back to the gpt2 estimator rather than returning 0 or raising."""
    for name in ("glm-5", "kimi-k2.5", "deepseek-v4-pro", "MiniMax-M2.5"):
        num_tokens = _model().get_num_tokens(name, {}, _messages())
        assert num_tokens > 0, f"{name} should fall back to a non-zero estimate"


def test_customizable_model_falls_back_to_gpt2():
    """A user-defined customizable model (arbitrary name) must still yield a
    usable non-zero estimate."""
    num_tokens = _model().get_num_tokens(
        "my-custom-openai-compatible-model",
        {"context_size": 4096, "function_calling_type": "tool_call"},
        _messages(),
    )
    assert num_tokens > 0


def test_chat_suffix_model_is_normalized():
    """qwen-plus-chat must be normalized to qwen-plus and tokenized."""
    num_tokens = _model().get_num_tokens("qwen-plus-chat", {}, _messages())
    assert num_tokens > 0


def test_farui_plus_is_normalized():
    """farui-plus maps to qwen-farui-plus, which the qwen tokenizer supports."""
    num_tokens = _model().get_num_tokens("farui-plus", {}, _messages())
    assert num_tokens > 0


def test_empty_prompt_returns_zero():
    """Sanity: an empty prompt genuinely has zero tokens."""
    assert _model().get_num_tokens("qwen-max", {}, []) == 0
