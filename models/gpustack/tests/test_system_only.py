"""Exercise legacy System-only workflows through the public model entrypoint."""

# isort: off
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    UserPromptMessage,
)
from models.llm.llm import GPUStackLanguageModel
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from jinja2 import Environment, TemplateError

# isort: on


class SystemOnlyTests(unittest.TestCase):
    def setUp(self):
        self.model = GPUStackLanguageModel(model_schemas=[])
        self.credentials = {
            "endpoint_url": "http://gpustack.test/v1",
            "api_key": "test-key",
            "mode": "chat",
            "context_size": "8192",
        }

    def capture(self, messages, parameters=None):
        response = requests.Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content = json.dumps(
            {
                "object": "chat.completion",
                "choices": [
                    {"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode()
        with patch("requests.post", return_value=response) as post:
            list(
                self.model.invoke(
                    "test",
                    {**self.credentials, "structured_output_support": "supported"},
                    messages,
                    parameters or {},
                    stream=False,
                )
            )
        return json.loads(post.call_args.kwargs["data"])

    def test_system_only_workflow_gets_an_execution_turn_without_changing_rules(self):
        messages = [SystemPromptMessage(content="Review only the supplied document. Return JSON.")]
        original = messages[0].model_dump()
        payload = self.capture(messages)
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])
        self.assertEqual(payload["messages"][0]["content"], messages[0].content)
        self.assertTrue(payload["messages"][1]["content"].strip())
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].model_dump(), original)

    def test_existing_user_turn_is_preserved(self):
        payload = self.capture(
            [
                SystemPromptMessage(content="Follow these rules."),
                UserPromptMessage(content="Review this actual input."),
            ]
        )
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "Follow these rules."},
                {"role": "user", "content": "Review this actual input."},
            ],
        )

    def test_preflight_token_estimate_receives_the_execution_turn(self):
        messages = [SystemPromptMessage(content="Review the supplied document.")]
        with patch.object(OAICompatLargeLanguageModel, "get_num_tokens", return_value=7) as counter:
            self.model.get_num_tokens("test", self.credentials.copy(), messages)
        prepared = counter.call_args.args[2]
        self.assertEqual([m.role.value for m in prepared], ["system", "user"])
        self.assertEqual(len(messages), 1)

    def test_multiple_system_messages_preserve_order_but_qwen_template_rejects(self):
        messages = [
            SystemPromptMessage(content="Follow the review rules."),
            SystemPromptMessage(content="Use the required output format."),
        ]
        originals = [message.model_dump() for message in messages]
        payload = self.capture(messages)
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "system", "user"])
        self.assertEqual(
            [m["content"] for m in payload["messages"][:2]],
            [message.content for message in messages],
        )
        self.assertEqual([message.model_dump() for message in messages], originals)

        # Frozen official template keeps this contract check offline.
        template_path = Path(__file__).parent / "fixtures" / "qwen35-chat-template.jinja"
        environment = Environment()

        def reject(message):
            raise TemplateError(message)

        environment.globals["raise_exception"] = reject
        template = environment.from_string(template_path.read_text(encoding="utf-8"))
        single = self.capture([SystemPromptMessage(content="Follow the review rules.")])
        template.render(messages=single["messages"], tools=[], add_generation_prompt=True)
        with self.assertRaisesRegex(TemplateError, r"^System message must be at the beginning\.$"):
            template.render(messages=payload["messages"], tools=[], add_generation_prompt=True)

    def test_completion_token_estimation_keeps_the_original_messages(self):
        self.credentials["mode"] = "completion"
        messages = [SystemPromptMessage(content="Complete this text.")]
        with patch.object(
            self.model, "_handle_generate_response", wraps=self.model._handle_generate_response
        ) as handler:
            self.capture(messages)
        self.assertEqual([m.role.value for m in handler.call_args.args[3]], ["system"])

    def test_system_only_json_schema_retains_rules_and_execution_turn(self):
        schema = {"name": "answer", "schema": {"type": "object", "properties": {}}}
        payload = self.capture(
            [SystemPromptMessage(content="Review the provided document.")],
            {"response_format": "json_schema", "json_schema": json.dumps(schema)},
        )
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])
        self.assertIn("Review the provided document.", payload["messages"][0]["content"])
        self.assertEqual(payload["response_format"]["json_schema"], schema)

    def test_json_schema_instruction_alone_does_not_create_a_task(self):
        schema = {"name": "answer", "schema": {"type": "object", "properties": {}}}
        messages = []
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                payload = self.capture(
                    messages, {"response_format": "json_schema", "json_schema": json.dumps(schema)}
                )
                self.assertFalse(any(m["role"] == "user" for m in payload["messages"]))
        self.assertEqual(messages, [])

    def test_no_execution_turn_is_invented_for_empty_or_assistant_only_inputs(self):
        for messages in [
            [],
            [SystemPromptMessage(content=" ")],
            [AssistantPromptMessage(content="Old response")],
        ]:
            with self.subTest(messages=messages):
                payload = self.capture(messages)
                self.assertFalse(any(m["role"] == "user" for m in payload["messages"]))


if __name__ == "__main__":
    unittest.main()
