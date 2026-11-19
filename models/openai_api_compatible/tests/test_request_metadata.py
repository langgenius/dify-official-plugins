from unittest.mock import patch

from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage

from models.llm.llm import DIFY_APP_ID_HEADER, DIFY_USER_ID_HEADER, OpenAILargeLanguageModel

SUPER = "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke"


def _prompt_messages():
    return [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(content="Hello"),
    ]


def _captured_credentials(credentials: dict, *, user: str | None = "user-123", app_id: str | None = "app-456"):
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["credentials"] = dict(credentials)
        return iter([])

    with (
        patch(SUPER, new=fake_super),
        patch("models.llm.llm._current_app_id", return_value=app_id),
    ):
        model._invoke(
            model="gpt-4o-mini",
            credentials={"mode": "chat", **credentials},
            prompt_messages=_prompt_messages(),
            model_parameters={},
            stream=True,
            user=user,
        )

    return captured["credentials"]


def test_metadata_headers_are_not_sent_by_default():
    credentials = _captured_credentials({})

    assert "extra_headers" not in credentials


def test_metadata_headers_are_sent_when_enabled():
    credentials = _captured_credentials({"enable_request_metadata": "enabled"})

    assert credentials["extra_headers"] == {
        DIFY_APP_ID_HEADER: "app-456",
        DIFY_USER_ID_HEADER: "user-123",
    }


def test_existing_credential_headers_are_preserved():
    credentials = _captured_credentials(
        {
            "enable_request_metadata": "enabled",
            "extra_headers": {"x-static": "from-credential"},
        }
    )

    assert credentials["extra_headers"] == {
        "x-static": "from-credential",
        DIFY_APP_ID_HEADER: "app-456",
        DIFY_USER_ID_HEADER: "user-123",
    }


def test_only_available_identifiers_are_sent():
    credentials = _captured_credentials({"enable_request_metadata": "enabled"}, user=None, app_id=None)

    assert "extra_headers" not in credentials

    app_only = _captured_credentials({"enable_request_metadata": "enabled"}, user=None)
    assert app_only["extra_headers"] == {DIFY_APP_ID_HEADER: "app-456"}


def test_model_parameter_headers_still_win():
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["credentials"] = dict(credentials)
        return iter([])

    with (
        patch(SUPER, new=fake_super),
        patch("models.llm.llm._current_app_id", return_value="app-456"),
    ):
        model._invoke(
            model="gpt-4o-mini",
            credentials={"mode": "chat", "enable_request_metadata": "enabled"},
            prompt_messages=_prompt_messages(),
            model_parameters={"extra_headers": '{"x-dify-app-id": "explicit"}'},
            stream=True,
            user="user-123",
        )

    assert captured["credentials"]["extra_headers"][DIFY_APP_ID_HEADER] == "explicit"
