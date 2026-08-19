from unittest.mock import MagicMock, patch

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


def test_invoke_injects_stream_options_when_streaming():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["model_parameters"] = dict(model_parameters)
        captured["stream"] = stream
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="gpt-4o-mini",
            credentials={"mode": "chat"},
            prompt_messages=_prompt_messages(),
            model_parameters={"temperature": 0.7},
            stream=True,
        )

    assert captured["stream"] is True
    assert captured["model_parameters"].get("stream_options") == {"include_usage": True}


def test_invoke_does_not_inject_stream_options_when_not_streaming():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["model_parameters"] = dict(model_parameters)
        captured["stream"] = stream
        return MagicMock()

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="gpt-4o-mini",
            credentials={"mode": "chat"},
            prompt_messages=_prompt_messages(),
            model_parameters={"temperature": 0.7},
            stream=False,
        )

    assert captured["stream"] is False
    assert "stream_options" not in captured["model_parameters"]


def test_invoke_respects_user_provided_stream_options():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["model_parameters"] = dict(model_parameters)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="gpt-4o-mini",
            credentials={"mode": "chat"},
            prompt_messages=_prompt_messages(),
            model_parameters={"stream_options": {"include_usage": False}},
            stream=True,
        )

    assert captured["model_parameters"].get("stream_options") == {"include_usage": False}


def test_invoke_honours_disabled_credential_opt_out():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["model_parameters"] = dict(model_parameters)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="gpt-4o-mini",
            credentials={"mode": "chat", "stream_include_usage": "disabled"},
            prompt_messages=_prompt_messages(),
            model_parameters={"temperature": 0.7},
            stream=True,
        )

    assert "stream_options" not in captured["model_parameters"]
