import hashlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dify_plugin.entities.model.message import (  # noqa: E402
    AssistantPromptMessage,
    AudioPromptMessageContent,
    DeveloperPromptMessage,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessageTool,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.entities.model.llm import LLMMode, LLMUsage  # noqa: E402
from dify_plugin.errors.model import (  # noqa: E402
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from models.llm.llm import (  # noqa: E402
    RESPONSES_OUTPUT_KEY,
    OpenAILargeLanguageModel,
    _normalize_service_tier_params,
    _uses_responses_api,
)


def make_llm() -> OpenAILargeLanguageModel:
    return object.__new__(OpenAILargeLanguageModel)


def make_response(
    *,
    output=None,
    output_text="",
    status="completed",
    usage=True,
    error=None,
    incomplete_reason=None,
):
    return SimpleNamespace(
        id="resp_1",
        model="gpt-5.6",
        output=output or [],
        output_text=output_text,
        status=status,
        usage=(SimpleNamespace(input_tokens=11, output_tokens=7) if usage else None),
        error=error,
        incomplete_details=(
            SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None
        ),
    )


def make_tool_call(call_id="call_1", name="lookup", arguments='{"q":"x"}'):
    return AssistantPromptMessage.ToolCall(
        id=call_id,
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name=name,
            arguments=arguments,
        ),
    )


def stub_usage(llm: OpenAILargeLanguageModel) -> None:
    llm._calc_response_usage = MagicMock(return_value=LLMUsage.empty_usage())


class TestResponsesApiRouting(unittest.TestCase):
    def test_provider_credential_schemas_default_to_responses(self):
        provider = yaml.safe_load((ROOT_DIR / "provider" / "openai.yaml").read_text())
        for schema_name in ("model_credential_schema", "provider_credential_schema"):
            fields = provider[schema_name]["credential_form_schemas"]
            protocol = next(field for field in fields if field["variable"] == "api_protocol")
            with self.subTest(schema=schema_name):
                self.assertEqual(protocol["default"], "responses")

    def test_responses_is_the_default_protocol(self):
        self.assertTrue(_uses_responses_api({}))
        self.assertTrue(_uses_responses_api({"api_protocol": None}))
        self.assertTrue(_uses_responses_api({"api_protocol": ""}))
        self.assertTrue(_uses_responses_api({"api_protocol": "responses"}))
        self.assertFalse(_uses_responses_api({"api_protocol": "chat"}))

    @patch("models.llm.llm.OpenAI")
    def test_gpt56_routes_to_responses_by_default(self, openai):
        llm = make_llm()
        expected = object()
        llm._chat_generate_responses_api = MagicMock(return_value=expected)

        result = llm._chat_generate(
            model="gpt-5.6-sol",
            credentials={"openai_api_key": "test"},
            prompt_messages=[UserPromptMessage(content="Hello")],
            model_parameters={"reasoning_effort": "medium"},
            stream=False,
        )

        self.assertIs(result, expected)
        llm._chat_generate_responses_api.assert_called_once()
        openai.return_value.chat.completions.create.assert_not_called()

    @patch("models.llm.llm.OpenAI")
    def test_gpt56_stream_routes_to_responses_without_protocol(self, openai):
        llm = make_llm()
        expected = object()
        llm._chat_generate_responses_api_stream = MagicMock(return_value=expected)

        result = llm._chat_generate(
            model="gpt-5.6-luna",
            credentials={"openai_api_key": "test"},
            prompt_messages=[UserPromptMessage(content="Hello")],
            model_parameters={},
            stream=True,
        )

        self.assertIs(result, expected)
        llm._chat_generate_responses_api_stream.assert_called_once()
        openai.return_value.chat.completions.create.assert_not_called()

    @patch("models.llm.llm.OpenAI")
    def test_chat_generation_does_not_mutate_caller_parameters(self, openai):
        llm = make_llm()
        llm._chat_generate_responses_api = MagicMock(return_value=object())
        parameters = {
            "service_tier": "default",
            "response_format": "json_object",
        }

        llm._chat_generate(
            model="gpt-5.6",
            credentials={"openai_api_key": "test"},
            prompt_messages=[UserPromptMessage(content="Hello")],
            model_parameters=parameters,
            stream=False,
        )

        self.assertEqual(
            parameters,
            {
                "service_tier": "default",
                "response_format": "json_object",
            },
        )

    @patch("models.llm.llm.OpenAI")
    def test_validate_credentials_uses_responses_for_gpt56(self, openai):
        llm = make_llm()
        with patch.object(
            OpenAILargeLanguageModel,
            "get_model_mode",
            return_value=LLMMode.CHAT,
        ):
            llm.validate_credentials(
                "gpt-5.6-terra",
                {"openai_api_key": "test"},
            )

        openai.return_value.responses.create.assert_called_once()
        openai.return_value.chat.completions.create.assert_not_called()

    @patch("models.llm.llm.OpenAI")
    def test_validate_completion_model_uses_completions_endpoint(self, openai):
        llm = make_llm()
        with patch.object(
            OpenAILargeLanguageModel,
            "get_model_mode",
            return_value=LLMMode.COMPLETION,
        ):
            llm.validate_credentials(
                "gpt-3.5-turbo-instruct",
                {"openai_api_key": "test"},
            )

        openai.return_value.completions.create.assert_called_once()
        openai.return_value.responses.create.assert_not_called()

    @patch("models.llm.llm.OpenAI")
    def test_validate_explicit_chat_does_not_fall_back_to_responses(self, openai):
        llm = make_llm()
        openai.return_value.chat.completions.create.side_effect = RuntimeError("chat failed")
        with (
            patch.object(
                OpenAILargeLanguageModel,
                "get_model_mode",
                return_value=LLMMode.CHAT,
            ),
            self.assertRaisesRegex(CredentialsValidateFailedError, "chat failed"),
        ):
            llm.validate_credentials(
                "gpt-4o",
                {"openai_api_key": "test", "api_protocol": "chat"},
            )

        openai.return_value.responses.create.assert_not_called()


class TestResponsesApiParameters(unittest.TestCase):
    def setUp(self):
        self.llm = make_llm()

    def test_reasoning_none_is_sent_explicitly(self):
        params = self.llm._build_responses_api_params({"reasoning_effort": "none"})
        self.assertEqual(params["reasoning"], {"effort": "none"})

    def test_service_tier_default_is_not_changed_to_auto(self):
        params = {"service_tier": "default"}
        _normalize_service_tier_params(params)
        self.assertEqual(params, {"service_tier": "default"})

        for empty_value in (None, ""):
            with self.subTest(empty_value=empty_value):
                params = {"service_tier": empty_value}
                _normalize_service_tier_params(params)
                self.assertNotIn("service_tier", params)

    def test_chat_only_neutral_penalties_are_removed(self):
        params = self.llm._build_responses_api_params(
            {"presence_penalty": 0.0, "frequency_penalty": 0}
        )
        self.assertNotIn("presence_penalty", params)
        self.assertNotIn("frequency_penalty", params)

    def test_chat_only_non_neutral_parameters_are_rejected(self):
        for parameter, value in (
            ("presence_penalty", 0.5),
            ("frequency_penalty", -0.5),
            ("seed", 0),
        ):
            with (
                self.subTest(parameter=parameter),
                self.assertRaisesRegex(InvokeBadRequestError, parameter),
            ):
                self.llm._build_responses_api_params({parameter: value})

    def test_responses_defaults_to_stateless_reasoning_replay(self):
        params = self.llm._build_responses_api_params({}, user="user-123")
        end_user_hash = hashlib.sha256(b"user-123").hexdigest()
        self.assertFalse(params["store"])
        self.assertEqual(params["include"], ["reasoning.encrypted_content"])
        self.assertEqual(params["safety_identifier"], end_user_hash)
        self.assertEqual(params["prompt_cache_key"], end_user_hash)
        self.assertNotIn("user", params)

    def test_chat_tool_choice_is_flattened_for_responses(self):
        params = self.llm._build_responses_api_params(
            {
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "lookup"},
                }
            }
        )
        self.assertEqual(
            params["tool_choice"],
            {"type": "function", "name": "lookup"},
        )

    def test_function_tools_preserve_chat_non_strict_behavior(self):
        tools = self.llm._build_responses_api_tools(
            [
                PromptMessageTool(
                    name="lookup",
                    description="Look up a value",
                    parameters={"type": "object", "properties": {}},
                )
            ]
        )
        self.assertEqual(tools[0]["strict"], False)

    def test_responses_parameters_are_mapped_and_merged(self):
        schema = {
            "name": "answer",
            "description": "A structured answer",
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
            "strict": True,
        }
        params = self.llm._build_responses_api_params(
            {
                "max_tokens": 2048,
                "reasoning_effort": "none",
                "response_format": {
                    "type": "json_schema",
                    "json_schema": schema,
                },
                "verbosity": "high",
                "service_tier": "auto",
            }
        )
        self.assertEqual(params["max_output_tokens"], 2048)
        self.assertEqual(params["reasoning"], {"effort": "none"})
        self.assertEqual(
            params["text"],
            {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "description": "A structured answer",
                    "schema": schema["schema"],
                    "strict": True,
                },
                "verbosity": "high",
            },
        )
        self.assertEqual(params["service_tier"], "auto")
        self.assertNotIn("max_tokens", params)
        self.assertNotIn("reasoning_effort", params)
        self.assertNotIn("response_format", params)
        self.assertNotIn("verbosity", params)


class TestResponsesApiInput(unittest.TestCase):
    def setUp(self):
        self.llm = make_llm()

    def test_developer_image_and_document_inputs_are_preserved(self):
        image = ImagePromptMessageContent(
            url="https://example.com/image.png",
            mime_type="image/png",
            format="png",
        )
        document = DocumentPromptMessageContent(
            url="https://example.com/context.pdf",
            mime_type="application/pdf",
            format="pdf",
        )
        result = self.llm._convert_prompt_messages_to_responses_input(
            [
                DeveloperPromptMessage(content="Follow policy"),
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="Question"),
                        image,
                        document,
                    ]
                ),
            ]
        )

        self.assertEqual(result[0]["role"], "developer")
        self.assertEqual(result[1]["content"][0], {"type": "input_text", "text": "Question"})
        self.assertEqual(
            result[1]["content"][1],
            {"type": "input_image", "image_url": "https://example.com/image.png"},
        )
        self.assertEqual(
            result[1]["content"][2],
            {"type": "input_file", "file_url": "https://example.com/context.pdf"},
        )

    def test_base64_document_includes_filename_and_data_url(self):
        document = DocumentPromptMessageContent(
            base64_data="SGVsbG8=",
            mime_type="application/pdf",
            format="pdf",
        )
        result = self.llm._convert_prompt_messages_to_responses_input(
            [UserPromptMessage(content=[document])]
        )
        self.assertEqual(
            result[0]["content"],
            [
                {
                    "type": "input_file",
                    "filename": "document.pdf",
                    "file_data": "data:application/pdf;base64,SGVsbG8=",
                }
            ],
        )

    def test_audio_input_is_rejected_instead_of_dropped(self):
        audio = AudioPromptMessageContent(
            base64_data="UklGRg==",
            mime_type="audio/wav",
            format="wav",
        )
        with self.assertRaisesRegex(InvokeBadRequestError, "audio input"):
            self.llm._convert_prompt_messages_to_responses_input(
                [UserPromptMessage(content=[audio])]
            )

    def test_assistant_text_and_tool_calls_are_both_preserved(self):
        result = self.llm._convert_prompt_messages_to_responses_input(
            [
                AssistantPromptMessage(
                    content="I will look that up.",
                    tool_calls=[make_tool_call()],
                )
            ]
        )
        self.assertEqual(
            [item["type"] for item in result],
            ["message", "function_call"],
        )
        self.assertEqual(result[0]["content"], "I will look that up.")
        self.assertEqual(result[1]["call_id"], "call_1")

    def test_assistant_multimodal_content_is_preserved(self):
        result = self.llm._convert_prompt_messages_to_responses_input(
            [AssistantPromptMessage(content=[TextPromptMessageContent(data="Prior answer")])]
        )
        self.assertEqual(
            result[0]["content"],
            [{"type": "input_text", "text": "Prior answer"}],
        )

    def test_multimodal_tool_output_uses_typed_content(self):
        result = self.llm._convert_prompt_messages_to_responses_input(
            [
                ToolPromptMessage(
                    tool_call_id="call_1",
                    content=[TextPromptMessageContent(data="result")],
                )
            ]
        )
        self.assertEqual(
            result[0]["output"],
            [{"type": "input_text", "text": "result"}],
        )

    def test_opaque_output_items_are_replayed_untouched(self):
        output_items = [
            {
                "id": "rs_1",
                "type": "reasoning",
                "encrypted_content": "encrypted",
                "summary": [],
            },
            {
                "id": "fc_1",
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"q":"x"}',
                "status": "completed",
            },
        ]
        result = self.llm._convert_prompt_messages_to_responses_input(
            [
                AssistantPromptMessage(
                    content="ignored fallback",
                    tool_calls=[make_tool_call()],
                    opaque_body={RESPONSES_OUTPUT_KEY: output_items},
                ),
                ToolPromptMessage(tool_call_id="call_1", content="done"),
            ]
        )
        self.assertEqual(result[:2], output_items)
        self.assertEqual(result[2]["type"], "function_call_output")

    def test_empty_messages_do_not_create_empty_content_arrays(self):
        result = self.llm._convert_prompt_messages_to_responses_input(
            [UserPromptMessage(content=[])]
        )
        self.assertEqual(result, [])


class TestResponsesApiResults(unittest.TestCase):
    def setUp(self):
        self.llm = make_llm()
        stub_usage(self.llm)
        self.prompt_messages = [UserPromptMessage(content="Hello")]

    def test_non_stream_preserves_reasoning_phase_and_tool_call(self):
        output = [
            {
                "id": "rs_1",
                "type": "reasoning",
                "encrypted_content": "encrypted",
                "summary": [],
            },
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "phase": "commentary",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Working", "annotations": []}],
            },
            {
                "id": "fc_1",
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"q":"x"}',
                "status": "completed",
            },
        ]
        client = MagicMock()
        client.responses.create.return_value = make_response(output=output)

        result = self.llm._chat_generate_responses_api(
            model="gpt-5.6",
            credentials={},
            prompt_messages=self.prompt_messages,
            model_parameters={},
            tools=None,
            client=client,
        )

        self.assertEqual(result.message.content, "Working")
        self.assertEqual(result.message.tool_calls[0].id, "call_1")
        self.assertEqual(result.message.opaque_body[RESPONSES_OUTPUT_KEY], output)
        replay = self.llm._convert_prompt_messages_to_responses_input(
            [
                result.message,
                ToolPromptMessage(tool_call_id="call_1", content="done"),
            ]
        )
        self.assertEqual(
            [item["type"] for item in replay],
            ["reasoning", "message", "function_call", "function_call_output"],
        )

    def test_non_stream_refusal_is_returned_as_content(self):
        output = [
            {
                "type": "message",
                "content": [{"type": "refusal", "refusal": "I cannot help."}],
            }
        ]
        client = MagicMock()
        client.responses.create.return_value = make_response(output=output)
        result = self.llm._chat_generate_responses_api(
            "gpt-5.6",
            {},
            self.prompt_messages,
            {},
            None,
            client,
        )
        self.assertEqual(result.message.content, "I cannot help.")

    def test_non_stream_stop_suppresses_hidden_state_and_tool_calls(self):
        output = [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "before<STOP>after",
                        "annotations": [],
                    }
                ],
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": "{}",
                "status": "completed",
            },
        ]
        client = MagicMock()
        client.responses.create.return_value = make_response(output=output)
        result = self.llm._chat_generate_responses_api(
            "gpt-5.6",
            {},
            self.prompt_messages,
            {},
            None,
            client,
            stop=["<STOP>"],
        )
        self.assertEqual(result.message.content, "before")
        self.assertEqual(result.message.tool_calls, [])
        self.assertIsNone(result.message.opaque_body)

    def test_non_stream_failed_response_raises(self):
        client = MagicMock()
        client.responses.create.return_value = make_response(
            status="failed",
            error=SimpleNamespace(code="server_error", message="boom"),
        )
        with self.assertRaisesRegex(InvokeServerUnavailableError, "boom"):
            self.llm._chat_generate_responses_api(
                "gpt-5.6",
                {},
                self.prompt_messages,
                {},
                None,
                client,
            )

    def test_non_stream_incomplete_returns_partial_text_without_tool_call(self):
        output = [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "partial"}],
                "status": "incomplete",
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"unfinished":',
                "status": "incomplete",
            },
        ]
        client = MagicMock()
        client.responses.create.return_value = make_response(
            output=output,
            status="incomplete",
            incomplete_reason="max_output_tokens",
        )
        result = self.llm._chat_generate_responses_api(
            "gpt-5.6",
            {},
            self.prompt_messages,
            {},
            None,
            client,
        )
        self.assertEqual(result.message.content, "partial")
        self.assertEqual(result.message.tool_calls, [])
        self.assertEqual(result.message.opaque_body[RESPONSES_OUTPUT_KEY], output)

    def test_non_stream_missing_usage_uses_local_estimate(self):
        client = MagicMock()
        client.responses.create.return_value = make_response(
            output_text="hello",
            usage=False,
        )
        self.llm._num_tokens_from_messages = MagicMock(return_value=5)
        self.llm._num_tokens_from_string = MagicMock(return_value=2)

        result = self.llm._chat_generate_responses_api(
            "gpt-5.6",
            {},
            self.prompt_messages,
            {},
            None,
            client,
        )

        self.assertIsNotNone(result.usage)
        self.llm._calc_response_usage.assert_called_once_with(
            model="gpt-5.6",
            credentials={},
            prompt_tokens=5,
            completion_tokens=2,
        )


class TestResponsesApiStreaming(unittest.TestCase):
    def setUp(self):
        self.llm = make_llm()
        stub_usage(self.llm)
        self.prompt_messages = [UserPromptMessage(content="Hello")]

    def invoke(self, events, *, stop=None):
        client = MagicMock()
        client.responses.create.return_value = iter(events)
        return list(
            self.llm._chat_generate_responses_api_stream(
                model="gpt-5.6",
                credentials={},
                prompt_messages=self.prompt_messages,
                model_parameters={},
                tools=None,
                client=client,
                stop=stop,
            )
        )

    def test_stop_sequence_spanning_deltas_is_not_emitted(self):
        response = make_response(
            output=[
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "before<STOP>after",
                            "annotations": [],
                        }
                    ],
                }
            ]
        )
        chunks = self.invoke(
            [
                SimpleNamespace(type="response.output_text.delta", delta="before<ST"),
                SimpleNamespace(type="response.output_text.delta", delta="OP>after"),
                SimpleNamespace(type="response.completed", response=response),
            ],
            stop=["<STOP>"],
        )
        visible = "".join(chunk.delta.message.get_text_content() for chunk in chunks)
        self.assertEqual(visible, "before")
        self.assertEqual(chunks[-1].delta.finish_reason, "stop")
        self.assertIsNone(chunks[-1].delta.message.opaque_body)

    def test_refusal_delta_is_streamed(self):
        response = make_response(
            output=[
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "Cannot comply"}],
                }
            ]
        )
        chunks = self.invoke(
            [
                SimpleNamespace(type="response.refusal.delta", delta="Cannot comply"),
                SimpleNamespace(type="response.completed", response=response),
            ]
        )
        self.assertEqual(chunks[0].delta.message.content, "Cannot comply")

    def test_completed_tool_call_has_one_terminal_chunk(self):
        response = make_response(
            output=[
                {
                    "id": "fc_1",
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": '{"q":"x"}',
                    "status": "completed",
                }
            ]
        )
        chunks = self.invoke([SimpleNamespace(type="response.completed", response=response)])
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].delta.finish_reason, "tool_calls")
        self.assertEqual(chunks[0].delta.message.tool_calls[0].id, "call_1")
        self.assertIsNotNone(chunks[0].delta.usage)

    def test_incomplete_stream_exposes_length_finish_reason(self):
        response = make_response(
            status="incomplete",
            incomplete_reason="max_output_tokens",
        )
        chunks = self.invoke([SimpleNamespace(type="response.incomplete", response=response)])
        self.assertEqual(chunks[-1].delta.finish_reason, "length")
        self.assertIsNotNone(chunks[-1].delta.message.opaque_body)

    def test_error_and_failed_events_raise(self):
        cases = [
            [SimpleNamespace(type="error", code="server_error", message="boom")],
            [
                SimpleNamespace(
                    type="response.failed",
                    response=make_response(
                        status="failed",
                        error=SimpleNamespace(code="server_error", message="boom"),
                    ),
                )
            ],
        ]
        for events in cases:
            with (
                self.subTest(event=events[0].type),
                self.assertRaisesRegex(InvokeServerUnavailableError, "boom"),
            ):
                self.invoke(events)

    def test_invalid_prompt_stream_error_is_a_bad_request(self):
        with self.assertRaisesRegex(InvokeBadRequestError, "invalid_prompt"):
            self.invoke(
                [
                    SimpleNamespace(
                        type="error",
                        code="invalid_prompt",
                        message="bad input",
                    )
                ]
            )

    def test_rate_limit_stream_error_is_classified(self):
        with self.assertRaisesRegex(InvokeRateLimitError, "rate_limit_exceeded"):
            self.invoke(
                [
                    SimpleNamespace(
                        type="error",
                        code="rate_limit_exceeded",
                        message="slow down",
                    )
                ]
            )

    def test_stream_without_terminal_event_raises(self):
        with self.assertRaises(InvokeConnectionError):
            self.invoke([SimpleNamespace(type="response.output_text.delta", delta="partial")])


if __name__ == "__main__":
    unittest.main()
