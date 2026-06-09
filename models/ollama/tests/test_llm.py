from unittest import TestCase
from unittest.mock import Mock, patch

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)

from models.ollama.models.llm.llm import OllamaLargeLanguageModel


class TestOllamaLargeLanguageModel(TestCase):
    def setUp(self):
        self.model = OllamaLargeLanguageModel(model_schemas=[])

    def test_normalize_think_parameter_supports_booleans_and_levels(self):
        self.assertTrue(self.model._normalize_think_parameter(True))
        self.assertFalse(self.model._normalize_think_parameter("false"))
        self.assertEqual(self.model._normalize_think_parameter("high"), "high")
        self.assertEqual(self.model._normalize_think_parameter("MEDIUM"), "medium")

    def test_chat_payload_sends_top_level_think_level(self):
        response = Mock()
        response.status_code = 200
        response.text = ""

        with (
            patch("models.ollama.models.llm.llm.requests.post", return_value=response) as post,
            patch.object(self.model, "_handle_generate_response", return_value="ok"),
        ):
            result = self.model._generate(
                model="gpt-oss",
                credentials={"base_url": "http://localhost:11434", "mode": "chat"},
                prompt_messages=[UserPromptMessage(content="hi")],
                model_parameters={"think": False, "think_level": "high", "num_predict": 8},
                stream=False,
            )

        self.assertEqual(result, "ok")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["think"], "high")
        self.assertNotIn("think", payload["options"])
        self.assertNotIn("think_level", payload["options"])
        self.assertEqual(payload["options"]["num_predict"], 8)

    def test_assistant_and_tool_messages_use_ollama_tool_shape(self):
        tool_call = AssistantPromptMessage.ToolCall(
            id="get_temperature",
            type="function",
            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                name="get_temperature",
                arguments='{"city": "New York"}',
            ),
        )
        assistant = AssistantPromptMessage(
            content="<think>\nchecking\n</think>The answer needs a tool.",
            tool_calls=[tool_call],
        )

        assistant_dict = self.model._convert_prompt_message_to_dict(assistant)

        self.assertEqual(assistant_dict["role"], "assistant")
        self.assertEqual(assistant_dict["thinking"], "checking")
        self.assertEqual(assistant_dict["content"], "The answer needs a tool.")
        self.assertEqual(assistant_dict["tool_calls"][0]["function"]["name"], "get_temperature")
        self.assertEqual(
            assistant_dict["tool_calls"][0]["function"]["arguments"],
            {"city": "New York"},
        )

        tool_dict = self.model._convert_prompt_message_to_dict(
            ToolPromptMessage(content="22 C", tool_call_id="get_temperature")
        )

        self.assertEqual(tool_dict["role"], "tool")
        self.assertEqual(tool_dict["tool_name"], "get_temperature")
        self.assertEqual(tool_dict["tool_call_id"], "get_temperature")

    def test_merge_and_split_thinking_content(self):
        merged = self.model._merge_thinking_content("answer", "reasoning")

        self.assertEqual(merged, "<think>\nreasoning\n</think>answer")
        self.assertEqual(
            self.model._split_thinking_from_content(merged),
            ("reasoning", "answer"),
        )
