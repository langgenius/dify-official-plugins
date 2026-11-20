from unittest.mock import patch

from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    UserPromptMessage,
)

from models.llm.llm import OpenAILargeLanguageModel


def _prompt_messages():
    return [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(content="Hello, how are you?"),
    ]


def _invoke(credentials, model_parameters=None, user="end-user-1"):
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["model_parameters"] = dict(model_parameters)
        captured["user"] = user
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="@preset/sonnet-5-5",
            credentials=credentials,
            prompt_messages=_prompt_messages(),
            model_parameters=model_parameters if model_parameters is not None else {"temperature": 0.7},
            stream=True,
            user=user,
        )
    return captured


def test_prompt_cache_is_off_by_default():
    captured = _invoke({"mode": "chat"})

    assert "cache_control" not in captured["model_parameters"]
    assert "session_id" not in captured["model_parameters"]


def test_prompt_cache_auto_sends_ephemeral_cache_control_and_session_id():
    captured = _invoke({"mode": "chat", "prompt_cache": "auto"})

    assert captured["model_parameters"]["cache_control"] == {"type": "ephemeral"}
    assert captured["model_parameters"]["session_id"] == "end-user-1"


def test_prompt_cache_auto_1h_sets_one_hour_ttl():
    captured = _invoke({"mode": "chat", "prompt_cache": "auto_1h"})

    assert captured["model_parameters"]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_prompt_cache_without_user_sends_no_session_id():
    captured = _invoke({"mode": "chat", "prompt_cache": "auto"}, user=None)

    assert captured["model_parameters"]["cache_control"] == {"type": "ephemeral"}
    assert "session_id" not in captured["model_parameters"]


def test_prompt_cache_skips_session_id_when_user_identity_is_suppressed():
    captured = _invoke({"mode": "chat", "prompt_cache": "auto", "user_identity_support": "no_support"})

    assert captured["model_parameters"]["cache_control"] == {"type": "ephemeral"}
    assert "session_id" not in captured["model_parameters"]
    assert captured["user"] is None


def test_prompt_cache_keeps_caller_cache_control_and_session_id():
    captured = _invoke(
        {"mode": "chat", "prompt_cache": "auto_1h"},
        model_parameters={"cache_control": {"type": "ephemeral"}, "session_id": "conv-9"},
    )

    assert captured["model_parameters"]["cache_control"] == {"type": "ephemeral"}
    assert captured["model_parameters"]["session_id"] == "conv-9"
