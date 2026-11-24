import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    TextPromptMessageContent,
)
from dify_plugin.entities.tool import ToolInvokeMessage, ToolProviderType
from dify_plugin.file.file import File, FileType
from dify_plugin.interfaces.agent import AgentModelConfig, ToolEntity

from strategies.function_calling import (
    FunctionCallingAgentStrategy,
    FunctionCallingParams,
)
from strategies.tool_response import should_forward_file_message


def _make_tool_call(
    tool_call_id: str, name: str, arguments: str
) -> AssistantPromptMessage.ToolCall:
    return AssistantPromptMessage.ToolCall(
        id=tool_call_id,
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name=name,
            arguments=arguments,
        ),
    )


class TestFunctionCallingToolCallParsing(unittest.TestCase):
    def setUp(self):
        self.strategy = FunctionCallingAgentStrategy(
            runtime=Mock(), session=Mock()
        )

    def test_parse_tool_call_arguments_valid_json(self):
        self.assertEqual(
            FunctionCallingAgentStrategy._parse_tool_call_arguments('{"city": "Paris"}'),
            {"city": "Paris"},
        )

    def test_parse_tool_call_arguments_empty_string(self):
        self.assertEqual(
            FunctionCallingAgentStrategy._parse_tool_call_arguments(""),
            {},
        )

    def test_parse_tool_call_arguments_none(self):
        self.assertEqual(
            FunctionCallingAgentStrategy._parse_tool_call_arguments(None),
            {},
        )

    def test_parse_tool_call_arguments_malformed_json_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            FunctionCallingAgentStrategy._parse_tool_call_arguments('{"city": "Par')

        message = str(ctx.exception)
        self.assertIn("Failed to parse tool-call arguments as JSON", message)
        self.assertIn("truncated or malformed", message)
        self.assertIn("max_tokens", message)
        self.assertIsInstance(ctx.exception.__cause__, json.JSONDecodeError)

    def test_extract_tool_calls_valid_json(self):
        chunk = LLMResultChunk(
            model="test-model",
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(
                    content="",
                    tool_calls=[
                        _make_tool_call("call_1", "get_weather", '{"city": "Paris"}')
                    ],
                ),
            ),
        )

        tool_calls = self.strategy.extract_tool_calls(chunk)

        self.assertEqual(tool_calls, [("call_1", "get_weather", {"city": "Paris"})])

    def test_extract_tool_calls_malformed_json_raises_value_error(self):
        chunk = LLMResultChunk(
            model="test-model",
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(
                    content="",
                    tool_calls=[
                        _make_tool_call("call_1", "get_weather", '{"city": "Par')
                    ],
                ),
            ),
        )

        with self.assertRaises(ValueError) as ctx:
            self.strategy.extract_tool_calls(chunk)

        self.assertIn("Failed to parse tool-call arguments as JSON", str(ctx.exception))

    def test_extract_blocking_tool_calls_valid_json(self):
        result = LLMResult(
            model="test-model",
            message=AssistantPromptMessage(
                content="",
                tool_calls=[
                    _make_tool_call("call_1", "get_weather", '{"city": "Paris"}')
                ],
            ),
            usage=LLMUsage.empty_usage(),
        )

        tool_calls = self.strategy.extract_blocking_tool_calls(result)

        self.assertEqual(tool_calls, [("call_1", "get_weather", {"city": "Paris"})])

    def test_extract_blocking_tool_calls_malformed_json_raises_value_error(self):
        result = LLMResult(
            model="test-model",
            message=AssistantPromptMessage(
                content="",
                tool_calls=[
                    _make_tool_call("call_1", "get_weather", '{"city": "Par')
                ],
            ),
            usage=LLMUsage.empty_usage(),
        )

        with self.assertRaises(ValueError) as ctx:
            self.strategy.extract_blocking_tool_calls(result)

        self.assertIn("Failed to parse tool-call arguments as JSON", str(ctx.exception))

    def test_only_thinking_end_streams_after_tool_call(self):
        thinking_started = False
        streamed_content = []

        for function_call_state, content in [
            (False, "<think>\n"),
            (False, "Analyzing the request."),
            (True, "Hidden intermediate content"),
            (True, "\n</think>"),
        ]:
            should_stream, thinking_started = (
                self.strategy._get_streaming_content_state(
                    content=content,
                    function_call_state=function_call_state,
                    thinking_started=thinking_started,
                    iteration_step=1,
                    max_iteration_steps=3,
                )
            )
            if should_stream:
                streamed_content.append(content)

        response = "".join(streamed_content)
        self.assertEqual(
            response,
            "<think>\nAnalyzing the request.\n</think>",
        )
        self.assertFalse(thinking_started)


class TestFunctionCallingMultimodalPrompt(unittest.TestCase):
    def setUp(self):
        self.strategy = FunctionCallingAgentStrategy(
            runtime=Mock(), session=Mock()
        )
        self.strategy.query = "Describe the current image"

    @staticmethod
    def _file(file_type: FileType = FileType.IMAGE) -> File:
        file = File(
            url="https://example.invalid/test.png",
            mime_type="image/png" if file_type == FileType.IMAGE else "application/pdf",
            filename="test.png" if file_type == FileType.IMAGE else "test.pdf",
            extension=".png" if file_type == FileType.IMAGE else ".pdf",
            size=7,
            type=file_type,
        )
        file._blob = b"pngdata"
        return file

    def test_text_only_query_remains_string(self):
        self.strategy.files = []

        message = self.strategy._user_prompt_message

        self.assertEqual(message.content, "Describe the current image")

    def test_current_image_is_added_before_query_text(self):
        self.strategy.files = [self._file()]

        message = self.strategy._user_prompt_message

        self.assertIsInstance(message.content, list)
        self.assertEqual(len(message.content), 2)
        self.assertIsInstance(message.content[0], ImagePromptMessageContent)
        self.assertEqual(
            message.content[0].base64_data,
            base64.b64encode(b"pngdata").decode("ascii"),
        )
        self.assertEqual(message.content[0].detail, ImagePromptMessageContent.DETAIL.LOW)
        self.assertIsInstance(message.content[1], TextPromptMessageContent)
        self.assertEqual(message.content[1].data, "Describe the current image")

    def test_multiple_images_preserve_order(self):
        first = self._file()
        first.filename = "first.png"
        second = self._file()
        second.filename = "second.png"
        self.strategy.files = [first, second]

        message = self.strategy._user_prompt_message

        self.assertIsInstance(message.content, list)
        self.assertEqual(
            [content.filename for content in message.content[:-1]],
            ["first.png", "second.png"],
        )

    def test_non_image_files_are_not_added(self):
        self.strategy.files = [self._file(FileType.DOCUMENT)]

        message = self.strategy._user_prompt_message

        self.assertEqual(message.content, "Describe the current image")

    def test_empty_file_entries_from_dify_are_discarded(self):
        image = self._file()

        params = FunctionCallingParams(
            query="Describe the current image",
            instruction=None,
            model={
                "provider": "test/provider",
                "model": "test-model",
                "mode": "chat",
                "completion_params": {},
            },
            tools=None,
            files=[None, image],
        )

        self.assertEqual(params.files, [image])


class TestFunctionCallingToolResponseFormatting(unittest.TestCase):
    def test_workflow_keeps_text_and_omits_json_and_variable(self):
        responses = [
            ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.TEXT,
                message=ToolInvokeMessage.TextMessage(text='{"answer": "ok"}'),
            ),
            ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.JSON,
                message=ToolInvokeMessage.JsonMessage(
                    json_object={"answer": "ok"},
                ),
            ),
            ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.VARIABLE,
                message=ToolInvokeMessage.VariableMessage(
                    variable_name="answer",
                    variable_value="ok",
                ),
            ),
        ]

        result = "".join(
            FunctionCallingAgentStrategy._format_tool_response(
                response=response,
                provider_type=ToolProviderType.WORKFLOW,
            )
            for response in responses
        )

        self.assertEqual(result, '{"answer": "ok"}')

    def test_non_workflow_json_remains_visible(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.JSON,
            message=ToolInvokeMessage.JsonMessage(
                json_object={"answer": "ok"},
            ),
        )

        result = FunctionCallingAgentStrategy._format_tool_response(
            response=response,
            provider_type=ToolProviderType.BUILT_IN,
        )

        self.assertEqual(result, 'tool response: {"answer": "ok"}.')


class TestFunctionCallingFileForwarding(unittest.TestCase):
    @staticmethod
    def _tool() -> ToolEntity:
        return ToolEntity.model_validate(
            {
                "identity": {
                    "author": "test",
                    "name": "getfile",
                    "label": {"en_US": "getfile"},
                    "provider": "workflow-provider",
                },
                "provider_type": "workflow",
                "runtime_parameters": {},
            }
        )

    def _invoke_with_tool_response(self, response: ToolInvokeMessage) -> list[ToolInvokeMessage]:
        call = _make_tool_call("call-1", "getfile", '{"a":"get"}')
        session = Mock()
        session.model.llm.invoke.side_effect = [
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="", tool_calls=[call]),
                usage=LLMUsage.empty_usage(),
            ),
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="done", tool_calls=[]),
                usage=LLMUsage.empty_usage(),
            ),
        ]
        session.tool.invoke.return_value = iter([response])
        strategy = FunctionCallingAgentStrategy(runtime=Mock(), session=session)

        return list(
            strategy._invoke(
                {
                    "query": "get a file",
                    "instruction": "Use the tool",
                    "model": AgentModelConfig(provider="test", model="test-model", mode="chat"),
                    "tools": [self._tool()],
                    "maximum_iterations": 3,
                }
            )
        )

    def test_forwards_tool_file_link(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.LINK,
            message=ToolInvokeMessage.TextMessage(text="/files/tools/file-1.docx"),
            meta={"tool_file_id": "file-1", "mime_type": "application/octet-stream"},
        )

        messages = self._invoke_with_tool_response(response)

        self.assertIn(response, messages)

    def test_does_not_forward_plain_link(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.LINK,
            message=ToolInvokeMessage.TextMessage(text="https://dify.ai"),
        )

        messages = self._invoke_with_tool_response(response)

        self.assertNotIn(response, messages)

    def test_file_message_is_forwardable(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.FILE,
            message=None,
            meta={"file": {"transfer_method": "remote_url", "url": "https://example.test/report.pdf"}},
        )

        self.assertTrue(should_forward_file_message(response))


class TestFunctionCallingIterationLimit(unittest.TestCase):
    @staticmethod
    def _tool(name: str) -> ToolEntity:
        return ToolEntity.model_validate(
            {
                "identity": {
                    "author": "test",
                    "name": name,
                    "label": {"en_US": name},
                    "provider": "test",
                },
                "provider_type": "mcp",
                "runtime_parameters": {},
            }
        )

    def _run_until_limit(self, maximum_iterations: int):
        lookup = self._tool("lookup")
        call = _make_tool_call("call-1", "lookup", '{"q":"x"}')
        session = Mock()
        session.model.llm.invoke.side_effect = [
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="", tool_calls=[call]),
                usage=LLMUsage.empty_usage(),
            )
            for _ in range(maximum_iterations)
        ]
        session.tool.invoke.side_effect = lambda **kwargs: iter(
            [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text="result"),
                )
            ]
        )
        strategy = FunctionCallingAgentStrategy(runtime=Mock(), session=session)
        messages = list(
            strategy._invoke(
                {
                    "query": "keep looking",
                    "instruction": "Use the tools",
                    "model": AgentModelConfig(
                        provider="test", model="test-model", mode="chat"
                    ),
                    "tools": [lookup],
                    "maximum_iterations": maximum_iterations,
                }
            )
        )
        return session, messages

    def test_limit_message_is_visible_in_text_output(self):
        session, messages = self._run_until_limit(3)
        # rounds 1-2 execute the tool; the round-3 call is skipped
        self.assertEqual(session.tool.invoke.call_count, 2)
        text_output = "".join(
            m.message.text
            for m in messages
            if m.type == ToolInvokeMessage.MessageType.TEXT
        )
        # the limit must surface in the node output, not only in the log
        self.assertIn("Maximum iteration limit (3) reached", text_output)
        self.assertIn("lookup", text_output)

    def test_limit_message_lists_every_skipped_tool_call(self):
        lookup = self._tool("lookup")
        create_ticket = self._tool("create_ticket")
        calls = [
            _make_tool_call("call-1", "lookup", '{"q":"x"}'),
            _make_tool_call("call-2", "create_ticket", '{"id":"000"}'),
        ]
        session = Mock()
        session.model.llm.invoke.side_effect = [
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="", tool_calls=calls),
                usage=LLMUsage.empty_usage(),
            )
            for _ in range(2)
        ]
        session.tool.invoke.side_effect = lambda **kwargs: iter(
            [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text="result"),
                )
            ]
        )
        strategy = FunctionCallingAgentStrategy(runtime=Mock(), session=session)
        messages = list(
            strategy._invoke(
                {
                    "query": "do both",
                    "instruction": "Use the tools",
                    "model": AgentModelConfig(
                        provider="test", model="test-model", mode="chat"
                    ),
                    "tools": [lookup, create_ticket],
                    "maximum_iterations": 2,
                }
            )
        )
        self.assertEqual(session.tool.invoke.call_count, 2)
        text_output = "".join(
            m.message.text
            for m in messages
            if m.type == ToolInvokeMessage.MessageType.TEXT
        )
        self.assertIn("Maximum iteration limit (2) reached", text_output)
        self.assertIn("lookup", text_output)
        self.assertIn("create_ticket", text_output)


class TestFunctionCallingAllowedTools(unittest.TestCase):
    @staticmethod
    def _tool(name: str) -> ToolEntity:
        return ToolEntity.model_validate(
            {
                "identity": {
                    "author": "test",
                    "name": name,
                    "label": {"en_US": name},
                    "provider": "test",
                },
                "provider_type": "mcp",
                "runtime_parameters": {},
            }
        )

    def _invoke(self, allowed_tools):
        lookup = self._tool("lookup")
        create_ticket = self._tool("create_ticket")
        call = _make_tool_call(
            "call-1", "create_ticket", '{"id":"000"}'
        )
        session = Mock()
        session.model.llm.invoke.side_effect = [
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="", tool_calls=[call]),
                usage=LLMUsage.empty_usage(),
            ),
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="done", tool_calls=[]),
                usage=LLMUsage.empty_usage(),
            ),
        ]
        session.tool.invoke.return_value = iter(
            [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text="registered"),
                )
            ]
        )
        strategy = FunctionCallingAgentStrategy(runtime=Mock(), session=session)
        list(
            strategy._invoke(
                {
                    "query": "create a ticket",
                    "instruction": "Use the tools",
                    "model": AgentModelConfig(
                        provider="test", model="test-model", mode="chat"
                    ),
                    "tools": [lookup, create_ticket],
                    "allowed_tools": allowed_tools,
                    "maximum_iterations": 3,
                }
            )
        )
        return session.tool.invoke

    def test_unrestricted_invokes_the_requested_tool(self):
        invoke = self._invoke(None)
        invoke.assert_called()
        self.assertEqual(
            invoke.call_args.kwargs["tool_name"], "create_ticket"
        )

    def test_allowlist_blocks_tools_outside_the_list(self):
        invoke = self._invoke(["lookup"])
        invoke.assert_not_called()


class TestFunctionCallingToolErrorLogStatus(unittest.TestCase):
    """Issue #4321: failed tool calls must not be logged as success."""

    @staticmethod
    def _tool() -> ToolEntity:
        return ToolEntity.model_validate(
            {
                "identity": {
                    "author": "test",
                    "name": "slow_api",
                    "label": {"en_US": "slow_api"},
                    "provider": "test",
                },
                "provider_type": "api",
                "runtime_parameters": {},
            }
        )

    def _run(self, tool_name: str, tool_invoke_side_effect=None) -> list:
        call = _make_tool_call("call-1", tool_name, '{"q":"x"}')
        session = Mock()
        session.model.llm.invoke.side_effect = [
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="", tool_calls=[call]),
                usage=LLMUsage.empty_usage(),
            ),
            LLMResult(
                model="test-model",
                message=AssistantPromptMessage(content="done", tool_calls=[]),
                usage=LLMUsage.empty_usage(),
            ),
        ]
        if tool_invoke_side_effect is not None:
            session.tool.invoke.side_effect = tool_invoke_side_effect
        else:
            session.tool.invoke.return_value = iter(
                [
                    ToolInvokeMessage(
                        type=ToolInvokeMessage.MessageType.TEXT,
                        message=ToolInvokeMessage.TextMessage(text="ok"),
                    )
                ]
            )
        strategy = FunctionCallingAgentStrategy(runtime=Mock(), session=session)
        return list(
            strategy._invoke(
                {
                    "query": "call the tool",
                    "instruction": "Use the tool",
                    "model": AgentModelConfig(provider="test", model="test-model", mode="chat"),
                    "tools": [self._tool()],
                    "maximum_iterations": 3,
                }
            )
        )

    @staticmethod
    def _finished_call_log(messages: list, tool_name: str):
        logs = [
            m.message
            for m in messages
            if m.type == ToolInvokeMessage.MessageType.LOG
            and m.message.label == f"CALL {tool_name}"
            and m.message.status != ToolInvokeMessage.LogMessage.LogStatus.START
        ]
        assert len(logs) == 1, logs
        return logs[0]

    def test_timed_out_tool_call_is_logged_as_error(self):
        messages = self._run(
            "slow_api",
            tool_invoke_side_effect=TimeoutError(
                "read tool response failed: request failed: timed out"
            ),
        )

        log = self._finished_call_log(messages, "slow_api")
        self.assertEqual(log.status, ToolInvokeMessage.LogMessage.LogStatus.ERROR)
        self.assertIn("timed out", log.error)
        # the model still receives the error text as the tool result
        self.assertIn("tool invoke error", log.data["output"]["tool_response"])

    def test_successful_tool_call_is_logged_as_success(self):
        messages = self._run("slow_api")

        log = self._finished_call_log(messages, "slow_api")
        self.assertEqual(log.status, ToolInvokeMessage.LogMessage.LogStatus.SUCCESS)
        self.assertIsNone(log.error)

    def test_unknown_tool_call_is_logged_as_error(self):
        messages = self._run("missing_tool")

        log = self._finished_call_log(messages, "missing_tool")
        self.assertEqual(log.status, ToolInvokeMessage.LogMessage.LogStatus.ERROR)
        self.assertIn("there is not a tool named missing_tool", log.error)


if __name__ == "__main__":
    unittest.main()
