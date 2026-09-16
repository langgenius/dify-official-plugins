"""Protocol routing + Anthropic/Responses payload unit tests (no network)."""
from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

from models.llm import llm_anthropic, llm_responses
from models.llm.llm import OpenCodeGoLargeLanguageModel
from models.llm.session_headers import (
    public_headers_for_protocol,
    resolve_protocol,
)


def test_resolve_protocol_defaults_and_whitelists() -> None:
    assert resolve_protocol("glm-5.3-flash", {}) == "chat"
    assert resolve_protocol("union-alpha", {}) == "anthropic"
    assert resolve_protocol("grok-4.6", {}) == "responses"
    assert resolve_protocol("gpt-5.6-luna", {}) == "responses"
    assert resolve_protocol("muse-spark-1.3-contributor", {}) == "responses"
    # explicit credential wins
    assert resolve_protocol("union-alpha", {"api_protocol": "chat"}) == "chat"
    assert resolve_protocol("glm-5.3-flash", {"api_protocol": "anthropic"}) == "anthropic"


def test_public_headers_anthropic_drops_bearer() -> None:
    shared = {"User-Agent": "dify-opencode-go-plugin/0.2.0", "x-opencode-session": "s1"}
    headers = public_headers_for_protocol(shared, "sk-x", "anthropic")
    assert headers["x-api-key"] == "sk-x"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in headers
    assert headers["x-opencode-session"] == "s1"


def test_public_headers_responses_uses_bearer() -> None:
    shared = {
        "User-Agent": "dify-opencode-go-plugin/0.2.0",
        "x-opencode-session": "s1",
        "x-api-key": "should-be-removed",
        "anthropic-version": "should-be-removed",
    }
    headers = public_headers_for_protocol(shared, "sk-x", "responses")
    assert headers["Authorization"] == "Bearer sk-x"
    assert "x-api-key" not in headers
    assert "anthropic-version" not in headers


def test_anthropic_message_conversion() -> None:
    system, messages = llm_anthropic.build_messages_payload(
        [
            SystemPromptMessage(content="Be brief."),
            UserPromptMessage(content="Hi"),
            AssistantPromptMessage(
                content="Hello",
                tool_calls=[
                    AssistantPromptMessage.ToolCall(
                        id="call_1",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="lookup", arguments='{"q":1}'
                        ),
                    )
                ],
            ),
            ToolPromptMessage(content="result-ok", tool_call_id="call_1"),
        ]
    )
    assert system == "Be brief."
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert any(b.get("type") == "tool_use" for b in messages[1]["content"])
    assert messages[2]["role"] == "user"
    assert messages[2]["content"][0]["type"] == "tool_result"
    assert messages[2]["content"][0]["tool_use_id"] == "call_1"


def test_responses_input_conversion() -> None:
    items = llm_responses.build_input_payload(
        [
            SystemPromptMessage(content="sys"),
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(
                content="",
                tool_calls=[
                    AssistantPromptMessage.ToolCall(
                        id="call_9",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="search", arguments='{"k":"v"}'
                        ),
                    )
                ],
            ),
            ToolPromptMessage(content="found", tool_call_id="call_9"),
        ]
    )
    assert items[0] == {"role": "system", "content": "sys"}
    assert items[1] == {"role": "user", "content": "hi"}
    assert items[2]["type"] == "function_call"
    assert items[3]["type"] == "function_call_output"
    assert items[3]["call_id"] == "call_9"


def test_anthropic_non_stream_parse() -> None:
    data = {
        "id": "msg_1",
        "content": [
            {"type": "text", "text": "OK"},
            {"type": "tool_use", "id": "tu_1", "name": "t", "input": {"a": 1}},
        ],
        "usage": {"input_tokens": 12, "output_tokens": 3},
        "stop_reason": "tool_use",
    }
    text, tools, in_tok, out_tok, stop = llm_anthropic.parse_non_stream_response(data)
    assert text == "OK"
    assert tools[0].function.name == "t"
    assert in_tok == 12 and out_tok == 3
    assert stop == "tool_use"


def test_responses_non_stream_parse() -> None:
    data = {
        "id": "resp_1",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hi there"}],
            },
            {
                "type": "function_call",
                "call_id": "c1",
                "name": "fn",
                "arguments": '{"x":2}',
            },
        ],
        "usage": {"input_tokens": 5, "output_tokens": 7},
    }
    text, tools, in_tok, out_tok, status = llm_responses.parse_non_stream_response(data)
    assert text == "Hi there"
    assert tools[0].id == "c1"
    assert in_tok == 5 and out_tok == 7
    assert status == "completed"


def test_session_shared_across_protocols() -> None:
    session = MagicMock()
    session.conversation_id = "conv-protocol-share"
    session.session_id = "rpc-1"
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])

    captured: dict = {}

    def fake_anthropic(self, *args, **kwargs):
        # args order after self in _invoke_anthropic
        captured["anthropic_headers"] = kwargs.get("headers") or (
            args[6] if len(args) > 6 else None
        )
        return iter([])

    with patch("models.llm.llm.get_current_session", return_value=session):
        creds = {"api_key": "sk-test"}
        OpenCodeGoLargeLanguageModel._add_custom_parameters(creds, user="u")
        sid = creds["extra_headers"]["x-opencode-session"]
        assert sid == "conv-protocol-share"
        # same helper for all protocols
        a_headers = public_headers_for_protocol(
            creds["extra_headers"], "sk-test", "anthropic"
        )
        r_headers = public_headers_for_protocol(
            creds["extra_headers"], "sk-test", "responses"
        )
        assert a_headers["x-opencode-session"] == sid
        assert r_headers["x-opencode-session"] == sid
        assert "x-dify-run-id" not in a_headers
        assert "x-dify-run-id" not in r_headers


def test_run_id_never_sent_on_anthropic() -> None:
    with patch("models.llm.llm.get_current_session", return_value=None):
        creds = {
            "extra_headers": {
                "x-opencode-session": "",
                "x-dify-run-id": "11111111-2222-3333-4444-555555555555",
            }
        }
        OpenCodeGoLargeLanguageModel._add_custom_parameters(creds, user=None)
    headers = creds["extra_headers"]
    assert headers["x-opencode-session"] == "11111111-2222-3333-4444-555555555555"
    assert "x-dify-run-id" not in headers
    public = public_headers_for_protocol(headers, "sk", "anthropic")
    assert "x-dify-run-id" not in public
    assert public["x-api-key"] == "sk"


def test_invoke_routes_to_anthropic() -> None:
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    called = {}

    def fake_invoke_anthropic(self, *args, **kwargs):
        called["yes"] = True
        return iter([])

    with patch.object(
        OpenCodeGoLargeLanguageModel, "_invoke_anthropic", new=fake_invoke_anthropic
    ):
        model._invoke(
            model="union-alpha",
            credentials={"api_key": "sk-test"},
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={},
            stream=True,
            user=None,
        )
    assert called.get("yes") is True


def test_invoke_routes_to_responses() -> None:
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    called = {}

    def fake_invoke_responses(self, *args, **kwargs):
        called["yes"] = True
        return iter([])

    with patch.object(
        OpenCodeGoLargeLanguageModel, "_invoke_responses", new=fake_invoke_responses
    ):
        model._invoke(
            model="grok-4.6",
            credentials={"api_key": "sk-test"},
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={},
            stream=True,
            user=None,
        )
    assert called.get("yes") is True


def test_invoke_chat_default_still_uses_oai_compat() -> None:
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["model"] = model
        return iter([])

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="glm-5.3-flash",
            credentials={"api_key": "sk-test"},
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={},
            stream=True,
            user=None,
        )
    assert captured["model"] == "glm-5.3-flash"


def test_tools_payload_shapes() -> None:
    tools = [
        PromptMessageTool(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        )
    ]
    a_tools = llm_anthropic.build_tools_payload(tools)
    r_tools = llm_responses.build_tools_payload(tools)
    assert a_tools[0]["input_schema"]["type"] == "object"
    assert r_tools[0]["type"] == "function"
    assert r_tools[0]["name"] == "get_weather"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print("protocol tests OK", len(tests))
