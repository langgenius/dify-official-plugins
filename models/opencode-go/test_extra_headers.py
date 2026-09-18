"""Tests for LLM-node extra_headers (Dify-resolved {{#sys.*#}})."""
from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage
from dify_plugin.errors.model import InvokeError

from models.llm.llm import OpenCodeGoLargeLanguageModel


def _prompt_messages():
    return [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(content="Hello"),
    ]


def test_extra_headers_parameter_is_exposed_in_schema():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    schema = model.get_customizable_model_schema(
        "mimo-v2.5",
        {"mode": "chat", "context_size": "262144"},
    )
    param_names = [rule.name for rule in schema.parameter_rules]
    assert "extra_headers" in param_names


def test_parse_extra_headers_accepts_json_string():
    parsed = OpenCodeGoLargeLanguageModel._parse_extra_headers(
        '{"x-opencode-session": "run-abc"}'
    )
    assert parsed == {"x-opencode-session": "run-abc"}


def test_parse_extra_headers_accepts_dict():
    parsed = OpenCodeGoLargeLanguageModel._parse_extra_headers(
        {"x-trace-id": "trace-1"}
    )
    assert parsed == {"x-trace-id": "trace-1"}


def test_parse_extra_headers_rejects_invalid_json():
    try:
        OpenCodeGoLargeLanguageModel._parse_extra_headers("{not-json")
        raise AssertionError("expected InvokeError")
    except InvokeError as exc:
        assert "extra_headers" in str(exc)


def test_node_extra_headers_win_over_auto_session():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = dict(credentials)
        captured["model_parameters"] = dict(model_parameters)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test", "mode": "chat"},
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": '{"x-opencode-session": "20adfe56-bfa9-4b63-b474-e43a925790ee"}',
            },
            stream=True,
            user="e505052d-88f9-4cc9-84aa-741213cc11f7",
        )

    headers = captured["credentials"]["extra_headers"]
    assert headers["x-opencode-session"] == "20adfe56-bfa9-4b63-b474-e43a925790ee"
    assert headers["User-Agent"].startswith("dify-opencode-go-plugin/")
    assert "extra_headers" not in captured["model_parameters"]


def test_auto_session_used_when_node_headers_omit_session():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = dict(credentials)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ), patch("models.llm.llm.get_current_session", return_value=None):
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test", "mode": "chat"},
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": '{"x-trace-id": "trace-9"}',
            },
            stream=True,
            user="e505052d-88f9-4cc9-84aa-741213cc11f7",
        )

    headers = captured["credentials"]["extra_headers"]
    assert headers["x-trace-id"] == "trace-9"
    # Node extra_headers present without a session value — isolate per invoke
    # with a bare unique id (OpenCode only needs a stable per-conversation id).
    assert headers["x-opencode-session"]
    assert "e505052d" not in headers["x-opencode-session"]
    assert not headers["x-opencode-session"].startswith("dify-opencode-go/")


def test_empty_resolved_session_isolates_per_invoke():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    sessions = []

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        sessions.append(credentials["extra_headers"]["x-opencode-session"])
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ), patch("models.llm.llm.get_current_session", return_value=None):
        for _ in range(2):
            model._invoke(
                model="mimo-v2.5",
                credentials={"api_key": "sk-test"},
                prompt_messages=_prompt_messages(),
                model_parameters={
                    "extra_headers": '{"x-opencode-session": ""}',
                },
                stream=True,
                user="20162097",
            )

    assert sessions[0] != sessions[1]
    assert all(s for s in sessions)
    assert all("20162097" not in s for s in sessions)
    assert all(not s.startswith("dify-opencode-go/") for s in sessions)


def test_workflow_run_id_used_when_conversation_empty():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = dict(credentials)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test"},
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": (
                    '{"x-opencode-session": "", '
                    '"x-dify-run-id": "run-20adfe56-bfa9"}'
                ),
            },
            stream=True,
            user="20162097",
        )

    headers = captured["credentials"]["extra_headers"]
    assert headers["x-opencode-session"] == "run-20adfe56-bfa9"
    assert "x-dify-run-id" not in headers


def test_chatflow_prefers_conversation_over_run_id():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = dict(credentials)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test"},
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": (
                    '{"x-opencode-session": "conv-abc-12345", '
                    '"x-dify-run-id": "run-20adfe56-bfa9"}'
                ),
            },
            stream=True,
        )

    headers = captured["credentials"]["extra_headers"]
    assert headers["x-opencode-session"] == "conv-abc-12345"
    assert "x-dify-run-id" not in headers


def test_different_run_ids_produce_different_sessions():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    sessions = []

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        sessions.append(credentials["extra_headers"]["x-opencode-session"])
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        for run_id in ("run-00000001-aaaa", "run-00000002-bbbb"):
            model._invoke(
                model="mimo-v2.5",
                credentials={"api_key": "sk-test", "mode": "chat"},
                prompt_messages=_prompt_messages(),
                model_parameters={
                    "extra_headers": f'{{"x-opencode-session": "{run_id}"}}',
                },
                stream=True,
            )

    assert sessions[0] == "run-00000001-aaaa"
    assert sessions[1] == "run-00000002-bbbb"
    assert sessions[0] != sessions[1]


def test_unresolved_template_session_uses_run_id():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = dict(credentials)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ), patch("models.llm.llm.get_current_session", return_value=None):
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test"},
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": (
                    '{"x-opencode-session": "{{#sys.conversation_id#}}", '
                    '"x-dify-run-id": "971f9dbb-27e0-4981-bcb8-3a4472ac3fa6"}'
                ),
            },
            stream=True,
            user="a600164a",
        )

    sid = captured["credentials"]["extra_headers"]["x-opencode-session"]
    assert "{{" not in sid and "sys." not in sid
    assert sid == "971f9dbb-27e0-4981-bcb8-3a4472ac3fa6"


def test_unresolved_template_without_run_id_isolates():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = dict(credentials)
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ), patch("models.llm.llm.get_current_session", return_value=None):
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test"},
            prompt_messages=_prompt_messages(),
            model_parameters={
                "extra_headers": '{"x-opencode-session": "sys.conversation_id"}',
            },
            stream=True,
            user="a600164a",
        )

    sid = captured["credentials"]["extra_headers"]["x-opencode-session"]
    assert "sys." not in sid and "{{" not in sid
    assert sid


if __name__ == "__main__":
    test_extra_headers_parameter_is_exposed_in_schema()
    test_parse_extra_headers_accepts_json_string()
    test_parse_extra_headers_accepts_dict()
    test_parse_extra_headers_rejects_invalid_json()
    test_node_extra_headers_win_over_auto_session()
    test_auto_session_used_when_node_headers_omit_session()
    test_empty_resolved_session_isolates_per_invoke()
    test_workflow_run_id_used_when_conversation_empty()
    test_chatflow_prefers_conversation_over_run_id()
    test_different_run_ids_produce_different_sessions()
    test_unresolved_template_session_uses_run_id()
    test_unresolved_template_without_run_id_isolates()
    print("extra_headers tests OK")
