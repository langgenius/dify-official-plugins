import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dify_plugin.entities.model.message import UserPromptMessage  # noqa: E402
from dify_plugin.entities.model.llm import LLMMode  # noqa: E402
from models.llm.llm import OpenAILargeLanguageModel, _uses_responses_api  # noqa: E402


def make_llm() -> OpenAILargeLanguageModel:
    return object.__new__(OpenAILargeLanguageModel)


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


class TestResponsesApiParameters(unittest.TestCase):
    def setUp(self):
        self.llm = make_llm()

    def test_reasoning_none_is_sent_explicitly(self):
        params = self.llm._build_responses_api_params({"reasoning_effort": "none"})
        self.assertEqual(params["reasoning"], {"effort": "none"})

    def test_responses_parameters_are_mapped_and_merged(self):
        schema = {
            "name": "answer",
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


if __name__ == "__main__":
    unittest.main()
