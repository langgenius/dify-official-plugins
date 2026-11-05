"""Offline tests for OCILargeLanguageModel request shaping and response parsing.

Fixtures mirror payloads captured from the OCI Generative AI Inference API
(GENERIC, COHERE v1 and COHEREV2 formats). No network access is performed: the
OCI client is replaced by a fake whose ``base_client.call_api`` records the body.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import oci
import pytest
from dify_plugin.core.utils.yaml_loader import load_yaml_file
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm.llm import COHERE_V2_MODELS, Convertor, OCILargeLanguageModel  # noqa: E402

CREDENTIALS = {"authentication_method": "instance_principal_authentication", "compartment_ocid": "ocid1.compartment.oc1..example"}
PNG_1x1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _schemas() -> list[AIModelEntity]:
    provider = load_yaml_file(str(ROOT_DIR / "provider" / "oci.yaml"))
    entities = []
    for pattern in provider["models"]["llm"]["predefined"]:
        for path in sorted(ROOT_DIR.glob(pattern)):
            entities.append(AIModelEntity(**load_yaml_file(str(path))))
    return entities


@pytest.fixture(scope="module")
def model() -> OCILargeLanguageModel:
    return OCILargeLanguageModel(model_schemas=_schemas())


class _FakeResponse:
    def __init__(self, payload: dict | None = None, events: list[dict] | None = None):
        self.data = SimpleNamespace(
            text=json.dumps(payload) if payload is not None else None,
            events=lambda: [SimpleNamespace(data=json.dumps(e)) for e in (events or [])],
        )


def _fake_client(payload=None, events=None):
    """A real inference client (so request serialisation is genuine) whose HTTP layer is stubbed."""
    with patch("oci.config.validate_config"), patch("oci.base_client.validate_config", create=True):
        base_client = oci.base_client.BaseClient(
            "generative_ai_inference", {"region": "us-chicago-1"}, MagicMock(),
            oci.generative_ai_inference.models.generative_ai_inference_type_mapping,
        )
    base_client.call_api = MagicMock(return_value=_FakeResponse(payload, events))
    return SimpleNamespace(base_client=base_client)


def _sent_body(client) -> dict:
    return json.loads(client.base_client.call_api.call_args.kwargs["body"])


# ---------------------------------------------------------------------------
# Request shaping
# ---------------------------------------------------------------------------

def test_generic_request_uses_camelcase_uppercase_reasoning_effort(model):
    client = _fake_client(payload=_generic_payload("pong"))
    with patch.object(OCILargeLanguageModel, "_get_oci_credentials", return_value={"config": {}}), \
            patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client):
        model._generate("xai.grok-4.7", CREDENTIALS, [UserPromptMessage(content="ping")],
                        {"temperature": 0, "maxTokens": 64, "reasoningEffort": "low"}, stream=False)
    body = _sent_body(client)
    assert body["servingMode"] == {"servingType": "ON_DEMAND", "modelId": "xai.grok-4.7"}
    chat = body["chatRequest"]
    assert chat["apiFormat"] == "GENERIC"
    assert chat["reasoningEffort"] == "LOW"
    assert "reasoning_effort" not in chat
    assert chat["messages"][0] == {"role": "USER", "content": [{"type": "TEXT", "text": "ping"}]}


def test_legacy_snake_case_reasoning_effort_is_still_accepted(model):
    client = _fake_client(payload=_generic_payload("pong"))
    with patch.object(OCILargeLanguageModel, "_get_oci_credentials", return_value={"config": {}}), \
            patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client):
        model._generate("openai.gpt-oss-120b", CREDENTIALS, [UserPromptMessage(content="ping")],
                        {"reasoning_effort": "high"}, stream=False)
    assert _sent_body(client)["chatRequest"]["reasoningEffort"] == "HIGH"


def test_reasoning_effort_omitted_when_unset(model):
    client = _fake_client(payload=_generic_payload("pong"))
    with patch.object(OCILargeLanguageModel, "_get_oci_credentials", return_value={"config": {}}), \
            patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client):
        model._generate("xai.grok-4.20-reasoning", CREDENTIALS, [UserPromptMessage(content="ping")], {}, stream=False)
    assert "reasoningEffort" not in _sent_body(client)["chatRequest"]


def test_stream_requests_ask_for_usage(model):
    client = _fake_client(events=_generic_events("pong"))
    with patch.object(OCILargeLanguageModel, "_get_oci_credentials", return_value={"config": {}}), \
            patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client):
        list(model._generate("xai.grok-4.6", CREDENTIALS, [UserPromptMessage(content="ping")], {}, stream=True))
    chat = _sent_body(client)["chatRequest"]
    assert chat["isStream"] is True
    assert chat["streamOptions"] == {"isIncludeUsage": True}


def test_command_a_vision_uses_cohere_v2_format(model):
    client = _fake_client(payload=_cohere_v2_payload("Purple."))
    messages = [
        SystemPromptMessage(content="Be terse."),
        UserPromptMessage(content=[
            TextPromptMessageContent(data="What colour is this?"),
            ImagePromptMessageContent(base64_data=PNG_1x1, format="png", mime_type="image/png"),
        ]),
    ]
    with patch.object(OCILargeLanguageModel, "_get_oci_credentials", return_value={"config": {}}), \
            patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client):
        result = model._generate("cohere.command-a-vision", CREDENTIALS, messages, {"maxTokens": 16}, stream=False)
    chat = _sent_body(client)["chatRequest"]
    assert chat["apiFormat"] == "COHEREV2"
    assert chat["messages"][0] == {"role": "SYSTEM", "content": [{"type": "TEXT", "text": "Be terse."}]}
    assert chat["messages"][1]["role"] == "USER"
    assert chat["messages"][1]["content"][0] == {"type": "TEXT", "text": "What colour is this?"}
    assert chat["messages"][1]["content"][1] == {"type": "IMAGE_URL", "imageUrl": {"url": "data:image/png;base64," + PNG_1x1}}
    assert "message" not in chat and "chatHistory" not in chat  # v1-only fields must not leak
    assert result.message.content == "Purple."
    assert result.usage.prompt_tokens == 268 and result.usage.completion_tokens == 2


def test_other_cohere_models_keep_v1_format(model):
    assert "cohere.command-a-03-2025" not in COHERE_V2_MODELS
    payload = {"modelId": "cohere.command-a-03-2025", "chatResponse": {"apiFormat": "COHERE", "text": "pong", "toolCalls": None,
                                                                        "usage": {"promptTokens": 9, "totalTokens": 10}}}
    client = _fake_client(payload=payload)
    with patch.object(OCILargeLanguageModel, "_get_oci_credentials", return_value={"config": {}}), \
            patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client):
        result = model._generate("cohere.command-a-03-2025", CREDENTIALS,
                                 [SystemPromptMessage(content="sys"), UserPromptMessage(content="ping")], {}, stream=False)
    chat = _sent_body(client)["chatRequest"]
    assert chat["apiFormat"] == "COHERE"
    assert chat["message"] == "ping"
    assert chat["chatHistory"] == [{"role": "SYSTEM", "message": "sys"}]
    assert result.message.content == "pong"


def test_tools_rejected_for_models_without_tool_call_feature(model):
    tool = PromptMessageTool(name="t", description="d", parameters={"type": "object", "properties": {}})
    with pytest.raises(InvokeBadRequestError, match="does not support function calling"):
        model._generate("cohere.command-a-vision", CREDENTIALS, [UserPromptMessage(content="x")], {}, tools=[tool], stream=False)


def test_tools_allowed_for_tool_call_models(model):
    tool = PromptMessageTool(name="get_weather", description="Weather", parameters={"type": "object", "properties": {"city": {"type": "string"}}})
    client = _fake_client(payload=_generic_payload("pong"))
    with patch.object(OCILargeLanguageModel, "_get_oci_credentials", return_value={"config": {}}), \
            patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client):
        model._generate("xai.grok-4.7", CREDENTIALS, [UserPromptMessage(content="x")], {}, tools=[tool], stream=False)
    sent_tools = _sent_body(client)["chatRequest"]["tools"]
    assert sent_tools == [{"type": "FUNCTION", "name": "get_weather", "description": "Weather",
                           "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}]


# ---------------------------------------------------------------------------
# Cohere v2 message / tool conversion
# ---------------------------------------------------------------------------

def test_cohere_v2_assistant_and_tool_messages():
    convertor = Convertor()
    assistant = AssistantPromptMessage(content="", tool_calls=[AssistantPromptMessage.ToolCall(
        id="get_weather_abc", type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(name="get_weather", arguments='{"city": "Paris"}'))])
    oci_assistant = convertor._parse_prompt_message_to_cohere_v2(assistant)
    assert isinstance(oci_assistant, oci.generative_ai_inference.models.CohereAssistantMessageV2)
    assert oci_assistant.content is None
    assert oci_assistant.tool_calls[0].id == "get_weather_abc"
    assert oci_assistant.tool_calls[0].type == "FUNCTION"
    assert oci_assistant.tool_calls[0].function == {"name": "get_weather", "arguments": '{"city": "Paris"}'}

    tool_msg = convertor._parse_prompt_message_to_cohere_v2(
        ToolPromptMessage(content='{"temp_c": 18}', tool_call_id="get_weather_abc", name="get_weather"))
    assert isinstance(tool_msg, oci.generative_ai_inference.models.CohereToolMessageV2)
    assert tool_msg.tool_call_id == "get_weather_abc"
    assert tool_msg.content[0].text == '{"temp_c": 18}'


def test_cohere_v2_tool_definitions():
    tool = PromptMessageTool(name="get_weather", description="Weather", parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]})
    [oci_tool] = Convertor().convert_tools_to_cohere_v2([tool])
    assert oci_tool.type == "FUNCTION"
    assert oci_tool.function.name == "get_weather"
    assert oci_tool.function.parameters["required"] == ["city"]


@pytest.mark.parametrize(
    ("vendor", "calls", "expected"),
    [
        # Cohere v1: parameters dict
        ("cohere", [{"name": "get_weather", "parameters": {"city": "Paris"}}], ("get_weather", "get_weather", '{"city": "Paris"}')),
        # Cohere v2: nested function with JSON string arguments and a server id
        ("cohere", [{"id": "get_weather_x1", "type": "FUNCTION", "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'}}],
         ("get_weather_x1", "get_weather", '{"city":"Paris"}')),
        # Generic: flat name/arguments
        ("xai", [{"type": "FUNCTION", "id": "call_1", "name": "get_weather", "arguments": '{"city":"Paris"}'}],
         ("call_1", "get_weather", '{"city":"Paris"}')),
    ],
)
def test_convert_response_tool_calls(vendor, calls, expected):
    [call] = Convertor().convert_response_tool_calls(calls, vendor)
    assert (call.id, call.function.name, call.function.arguments) == expected


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _generic_payload(text: str) -> dict:
    return {"modelId": "xai.grok-4.7", "modelVersion": "1.0.0", "chatResponse": {
        "apiFormat": "GENERIC", "timeCreated": "2026-11-05T00:00:00Z",
        "choices": [{"index": 0, "message": {"role": "ASSISTANT", "content": [{"type": "TEXT", "text": text}]}, "finishReason": "stop"}],
        "usage": {"completionTokens": 1, "promptTokens": 1250, "totalTokens": 1316,
                  "completionTokensDetails": {"reasoningTokens": 65}, "promptTokensDetails": {"cachedTokens": 1152}}}}


def _cohere_v2_payload(text: str) -> dict:
    return {"modelId": "cohere.command-a-vision", "modelVersion": "1.0", "chatResponse": {
        "apiFormat": "COHEREV2", "id": "x", "message": {"role": "ASSISTANT", "content": [{"type": "TEXT", "text": text}], "citations": []},
        "finishReason": "COMPLETE", "usage": {"completionTokens": 2, "promptTokens": 268, "totalTokens": 270}}}


def _generic_events(text: str) -> list[dict]:
    return [
        {"message": {"role": "ASSISTANT", "content": [{"type": "TEXT", "text": text[:2]}]}, "pad": "aa"},
        {"message": {"role": "ASSISTANT", "content": [{"type": "TEXT", "text": text[2:]}]}, "pad": "a"},
        {"message": {"role": "ASSISTANT", "content": []}, "finishReason": "stop", "pad": "aaa"},
        {"usage": {"completionTokens": 1, "promptTokens": 10, "totalTokens": 20}},
    ]


def test_non_stream_generic_response_counts_reasoning_tokens_as_completion(model):
    result = model._handle_generate_response("xai.grok-4.7", CREDENTIALS, _generic_payload("pong"), [UserPromptMessage(content="ping")])
    assert result.message.content == "pong"
    assert result.usage.prompt_tokens == 1250
    assert result.usage.completion_tokens == 66  # total - prompt, includes reasoning tokens billed as output


def test_non_stream_generic_tool_call_response(model):
    payload = _generic_payload("")
    payload["chatResponse"]["choices"][0]["message"] = {"role": "ASSISTANT", "content": [], "toolCalls": [
        {"type": "FUNCTION", "id": "call_1", "name": "get_weather", "arguments": '{"city":"Paris"}'}]}
    payload["chatResponse"]["choices"][0]["finishReason"] = "tool_calls"
    result = model._handle_generate_response("xai.grok-4.7", CREDENTIALS, payload, [UserPromptMessage(content="ping")])
    assert result.message.content == ""
    assert [t.function.name for t in result.message.tool_calls] == ["get_weather"]


def test_non_stream_cohere_v2_tool_call_response(model):
    payload = _cohere_v2_payload("")
    payload["chatResponse"]["message"] = {"role": "ASSISTANT", "toolPlan": "I will use the tool.", "toolCalls": [
        {"id": "get_weather_gxs", "type": "FUNCTION", "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'}}]}
    payload["chatResponse"]["finishReason"] = "TOOL_CALL"
    result = model._handle_generate_response("cohere.command-a-03-2025", CREDENTIALS, payload, [UserPromptMessage(content="ping")])
    assert result.message.tool_calls[0].id == "get_weather_gxs"
    assert result.message.tool_calls[0].function.arguments == '{"city":"Paris"}'


def test_stream_generic_events(model):
    chunks = list(model._handle_generate_stream_response("xai.grok-4.7", CREDENTIALS, _FakeResponse(events=_generic_events("pong")), [UserPromptMessage(content="ping")]))
    assert "".join(c.delta.message.content or "" for c in chunks) == "pong"
    # no empty deltas, and exactly one terminal chunk carrying finish reason + usage
    assert all(c.delta.message.content or c.delta.message.tool_calls or c.delta.finish_reason or c.delta.usage for c in chunks)
    terminal = [c for c in chunks if c.delta.finish_reason]
    assert len(terminal) == 1
    assert terminal[0].delta.finish_reason == "stop"
    assert terminal[0].delta.usage.prompt_tokens == 10 and terminal[0].delta.usage.completion_tokens == 10


def test_stream_skips_done_sentinel_and_separate_usage_event(model):
    # Captured from meta.llama-4-scout-17b-16e-instruct: finish and usage arrive in separate
    # events and the stream ends with a literal "[DONE]" that is not JSON.
    events = [
        '{"index":0,"message":{"role":"ASSISTANT","content":[{"type":"TEXT","text":""}]},"pad":"aaaa"}',
        '{"index":0,"message":{"role":"ASSISTANT","content":[{"type":"TEXT","text":"pong"}]},"pad":"aaa"}',
        '{"message":{"role":"ASSISTANT"},"finishReason":"stop","pad":"aaaaaaaaaaa"}',
        '{"usage":{"completionTokens":2,"promptTokens":16,"totalTokens":18},"pad":"aaaaaaaa"}',
        '[DONE]',
    ]
    response = SimpleNamespace(data=SimpleNamespace(events=lambda: [SimpleNamespace(data=e) for e in events]))
    chunks = list(model._handle_generate_stream_response("meta.llama-4-scout-17b-16e-instruct", CREDENTIALS, response, [UserPromptMessage(content="ping")]))
    assert "".join(c.delta.message.content or "" for c in chunks) == "pong"
    assert chunks[-1].delta.finish_reason == "stop"
    assert chunks[-1].delta.usage.prompt_tokens == 16 and chunks[-1].delta.usage.completion_tokens == 2


def test_stream_accumulates_fragmented_tool_call(model):
    # Captured from openai.gpt-oss-120b: id/name once, then argument fragments, then finish + usage.
    events = [
        {"index": 0, "message": {"role": "ASSISTANT", "content": [{"type": "TEXT", "text": ""}]}},
        {"index": 0, "message": {"role": "ASSISTANT", "reasoningContent": "We need to call get_weather."}},
        {"index": 0, "message": {"role": "ASSISTANT", "toolCalls": [{"type": "FUNCTION", "id": "chatcmpl-tool-a71e", "name": "get_weather", "arguments": ""}]}},
        {"index": 0, "message": {"role": "ASSISTANT", "toolCalls": [{"type": "FUNCTION", "arguments": "{\n"}]}},
        {"index": 0, "message": {"role": "ASSISTANT", "toolCalls": [{"type": "FUNCTION", "arguments": " \"city\":"}]}},
        {"index": 0, "message": {"role": "ASSISTANT", "toolCalls": [{"type": "FUNCTION", "arguments": " \"Paris\"\n"}]}},
        {"index": 0, "message": {"role": "ASSISTANT", "toolCalls": [{"type": "FUNCTION", "arguments": "}"}]}},
        {"finishReason": "tool_calls"},
        {"usage": {"completionTokens": 39, "promptTokens": 130, "totalTokens": 169}},
    ]
    chunks = list(model._handle_generate_stream_response("openai.gpt-oss-120b", CREDENTIALS, _FakeResponse(events=events), [UserPromptMessage(content="ping")]))
    terminal = chunks[-1].delta
    assert terminal.finish_reason == "tool_calls"
    assert terminal.usage.prompt_tokens == 130
    [call] = terminal.message.tool_calls
    assert (call.id, call.function.name) == ("chatcmpl-tool-a71e", "get_weather")
    assert json.loads(call.function.arguments) == {"city": "Paris"}
    # no partial tool calls leaked into earlier deltas
    assert not any(c.delta.message.tool_calls for c in chunks[:-1])


def test_stream_complete_tool_call_and_parallel_calls(model):
    # Grok / Llama send whole tool calls; two different calls must stay separate.
    events = [
        {"index": 0, "message": {"role": "ASSISTANT", "toolCalls": [{"type": "FUNCTION", "id": "call-1", "name": "get_weather", "arguments": "{\"city\":\"Paris\"}"}]}},
        {"index": 0, "message": {"role": "ASSISTANT", "toolCalls": [{"type": "FUNCTION", "id": "call-2", "name": "get_time", "arguments": "{\"tz\":\"CET\"}"}]}},
        {"finishReason": "tool_calls"},
        {"usage": {"completionTokens": 11, "promptTokens": 1329, "totalTokens": 1365}},
    ]
    chunks = list(model._handle_generate_stream_response("xai.grok-4.7", CREDENTIALS, _FakeResponse(events=events), [UserPromptMessage(content="ping")]))
    calls = chunks[-1].delta.message.tool_calls
    assert [(c.id, c.function.name, c.function.arguments) for c in calls] == [
        ("call-1", "get_weather", '{"city":"Paris"}'),
        ("call-2", "get_time", '{"tz":"CET"}'),
    ]
    assert chunks[-1].delta.usage.completion_tokens == 36


def test_stream_cohere_v2_events(model):
    events = [
        {"apiFormat": "COHEREV2", "message": {"role": "ASSISTANT", "content": [{"type": "TEXT", "text": "Pur"}]}, "pad": "a"},
        {"apiFormat": "COHEREV2", "message": {"role": "ASSISTANT", "content": [{"type": "TEXT", "text": "ple."}]}, "pad": "aa"},
        {"apiFormat": "COHEREV2", "message": {"role": "ASSISTANT"}, "finishReason": "COMPLETE", "usage": {"completionTokens": 2, "promptTokens": 268, "totalTokens": 270}},
    ]
    chunks = list(model._handle_generate_stream_response("cohere.command-a-vision", CREDENTIALS, _FakeResponse(events=events), [UserPromptMessage(content="ping")]))
    assert "".join(c.delta.message.content for c in chunks) == "Purple."
    assert chunks[-1].delta.finish_reason == "COMPLETE"
    assert chunks[-1].delta.usage.prompt_tokens == 268 and chunks[-1].delta.usage.completion_tokens == 2


def test_stream_cohere_v1_events_unchanged(model):
    events = [{"text": "po", "pad": "a"}, {"text": "ng"}, {"finishReason": "COMPLETE", "usage": {"promptTokens": 9, "totalTokens": 10}}]
    chunks = list(model._handle_generate_stream_response("cohere.command-a-03-2025", CREDENTIALS, _FakeResponse(events=events), [UserPromptMessage(content="ping")]))
    assert "".join(c.delta.message.content for c in chunks) == "pong"
    assert chunks[-1].delta.finish_reason == "COMPLETE"


def test_join_text_content_tolerates_empty_and_non_text_parts():
    assert Convertor._join_text_content(None) == ""
    assert Convertor._join_text_content([]) == ""
    assert Convertor._join_text_content([{"type": "IMAGE_URL", "imageUrl": {"url": "x"}}, {"type": "TEXT", "text": "ok"}]) == "ok"
