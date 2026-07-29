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
from dify_plugin.entities.model.message import AssistantPromptMessage

from strategies.function_calling import FunctionCallingAgentStrategy


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


if __name__ == "__main__":
    unittest.main()
