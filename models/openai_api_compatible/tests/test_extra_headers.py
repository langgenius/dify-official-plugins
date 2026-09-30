from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeError

from models.llm.llm import OpenAILargeLanguageModel


def _prompt_messages():
    return [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(content="Hello"),
    ]


def test_extra_headers_parameter_is_exposed_in_schema():
    model = OpenAILargeLanguageModel(model_schemas=[])
    schema = model.get_customizable_model_schema(
        "gpt-4o-mini",
        {"mode": "chat", "context_size": "4096"},
    )
    param_names = [rule.name for rule in schema.parameter_rules]
    assert "extra_headers" in param_names


def test_parse_extra_headers_accepts_json_string():
    parsed = OpenAILargeLanguageModel._parse_extra_headers(
        '{"x-opencode-session": "abc-123"}'
    )
    assert parsed == {"x-opencode-session": "abc-123"}


def test_parse_extra_headers_accepts_dict():
    parsed = OpenAILargeLanguageModel._parse_extra_headers(
        {"x-trace-id": "trace-1"}
    )
    assert parsed == {"x-trace-id": "trace-1"}


def test_parse_extra_headers_rejects_invalid_json():
    try:
        OpenAILargeLanguageModel._parse_extra_headers("{not-json")
        raise AssertionError("expected InvokeError")
    except InvokeError as exc:
        assert "extra_headers" in str(exc)


def test_invoke_merges_extra_headers_into_credentials_for_chat_completions():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["credentials"] = dict(credentials)
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
            model_parameters={
                "extra_headers": '{"x-opencode-session": "conversation-abc"}',
            },
            stream=True,
        )

    assert captured["credentials"]["extra_headers"] == {
        "x-opencode-session": "conversation-abc",
    }
    assert "extra_headers" not in captured["model_parameters"]


def test_invoke_merges_model_parameter_headers_over_credential_headers():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["credentials"] = dict(credentials)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="gpt-4o-mini",
            credentials={
                "mode": "chat",
                "extra_headers": {"x-static": "from-credential"},
            },
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": '{"x-opencode-session": "conversation-abc"}',
            },
            stream=True,
        )

    assert captured["credentials"]["extra_headers"] == {
        "x-static": "from-credential",
        "x-opencode-session": "conversation-abc",
    }


def test_invoke_routes_extra_headers_to_responses_api_client():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_responses(self, **kwargs):
        captured["credentials"] = dict(kwargs["credentials"])
        return MagicMock()

    with patch.object(OpenAILargeLanguageModel, "_chat_generate_with_responses", fake_responses):
        model._invoke(
            model="gpt-4o-mini",
            credentials={"mode": "chat", "api_type": "responses"},
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": '{"x-opencode-session": "conversation-abc"}',
            },
            stream=False,
        )

    assert captured["credentials"]["extra_headers"] == {
        "x-opencode-session": "conversation-abc",
    }


def test_create_openai_client_forwards_extra_headers():
    model = OpenAILargeLanguageModel(model_schemas=[])
    with patch("models.llm.llm.OpenAI") as mock_openai:
        model._create_openai_client(
            {
                "api_key": "test-key",
                "endpoint_url": "https://example.com/v1",
                "extra_headers": {"x-opencode-session": "conversation-abc"},
            }
        )
        mock_openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.com/v1",
            default_headers={"x-opencode-session": "conversation-abc"},
        )
