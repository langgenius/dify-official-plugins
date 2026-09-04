"""Unit tests for the token parameter name mapping in OpenAILargeLanguageModel._invoke.

`token_param_name: auto` must decide between `max_tokens` and `max_completion_tokens`
from the model the endpoint actually receives — `endpoint_model_name` when it is set,
otherwise the Dify-side model name. This is the same resolution validate_credentials()
and the Responses API path already use.
"""

from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import OpenAILargeLanguageModel

SUPER_INVOKE = (
    "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke"
)


def _prompt_messages():
    return [UserPromptMessage(content="ping")]


def _capture_invoke(credentials, model="gpt-4o-mini", model_parameters=None):
    """Run _invoke with the base implementation stubbed out and return model_parameters."""
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
            model_parameters=dict(
                model_parameters if model_parameters is not None else {"max_tokens": 128}
            ),
            stream=False,
        )

    return captured["model_parameters"]


def test_auto_resolves_from_endpoint_model_name():
    """A non-gpt-5 Dify name must not hide a gpt-5 endpoint model."""
    params = _capture_invoke(
        {"mode": "chat", "endpoint_model_name": "gpt-5.6-luna", "token_param_name": "auto"},
        model="Luna",
    )

    assert params.get("max_completion_tokens") == 128
    assert "max_tokens" not in params


def test_auto_falls_back_to_model_when_no_endpoint_override():
    """Without endpoint_model_name the Dify-side model name is the endpoint model."""
    params = _capture_invoke({"mode": "chat", "token_param_name": "auto"}, model="gpt-5.6-luna")

    assert params.get("max_completion_tokens") == 128
    assert "max_tokens" not in params


def test_auto_does_not_map_when_endpoint_model_is_not_reasoning():
    """A gpt-5 Dify name must not force max_completion_tokens onto a non-gpt-5 deployment."""
    params = _capture_invoke(
        {"mode": "chat", "endpoint_model_name": "my-custom-deployment", "token_param_name": "auto"},
        model="gpt-5.6-luna",
    )

    assert params.get("max_tokens") == 128
    assert "max_completion_tokens" not in params


def test_auto_leaves_max_tokens_for_non_reasoning_models():
    params = _capture_invoke({"mode": "chat", "token_param_name": "auto"}, model="gpt-4o-mini")

    assert params.get("max_tokens") == 128
    assert "max_completion_tokens" not in params


def test_explicit_max_completion_tokens_overrides_detection():
    params = _capture_invoke(
        {"mode": "chat", "token_param_name": "max_completion_tokens"}, model="gpt-4o-mini"
    )

    assert params.get("max_completion_tokens") == 128
    assert "max_tokens" not in params


def test_explicit_max_tokens_disables_detection():
    params = _capture_invoke(
        {"mode": "chat", "endpoint_model_name": "gpt-5.6-luna", "token_param_name": "max_tokens"},
        model="gpt-5.6-luna",
    )

    assert params.get("max_tokens") == 128
    assert "max_completion_tokens" not in params


def test_existing_max_completion_tokens_is_preserved():
    """An explicit max_completion_tokens from the caller wins over the mapping."""
    params = _capture_invoke(
        {"mode": "chat", "endpoint_model_name": "gpt-5.6-luna", "token_param_name": "auto"},
        model="Luna",
        model_parameters={"max_tokens": 128, "max_completion_tokens": 256},
    )

    assert params.get("max_completion_tokens") == 256
    assert params.get("max_tokens") == 128
