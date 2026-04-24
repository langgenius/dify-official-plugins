"""
Tests for AzureOpenAILargeLanguageModel

Covers regression cases found in:
- Issue: gpt-5 + knowledge retrieval context → "Unsupported data type" from Azure
  Root cause: DocumentPromptMessageContent not handled in _convert_prompt_messages_to_responses_input,
  causing empty content arrays to be sent to the Responses API.
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from models.llm.llm import AzureOpenAILargeLanguageModel


def make_llm() -> AzureOpenAILargeLanguageModel:
    """Instantiate without calling __init__ (no credentials needed for unit tests)."""
    return object.__new__(AzureOpenAILargeLanguageModel)


class TestUsesResponsesApi(unittest.TestCase):
    def test_gpt5_uses_responses_api(self):
        self.assertTrue(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-5"))

    def test_gpt5_mini_uses_responses_api(self):
        self.assertTrue(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-5-mini"))

    def test_gpt5_nano_uses_responses_api(self):
        self.assertTrue(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-5-nano"))

    def test_gpt51_uses_responses_api(self):
        self.assertTrue(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-5.1"))

    def test_gpt5_chat_does_not_use_responses_api(self):
        """gpt-5-chat is a regular chat model, not reasoning → Chat Completions API."""
        self.assertFalse(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-5-chat"))

    def test_gpt4o_does_not_use_responses_api(self):
        self.assertFalse(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-4o"))

    def test_codex_uses_responses_api(self):
        self.assertTrue(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-5-codex"))

    def test_gpt51_codex_uses_responses_api(self):
        self.assertTrue(AzureOpenAILargeLanguageModel._uses_responses_api("gpt-5.1-codex"))

    def test_o1_does_not_use_responses_api(self):
        self.assertFalse(AzureOpenAILargeLanguageModel._uses_responses_api("o1"))


class TestConvertPromptMessagesToResponsesInput(unittest.TestCase):
    def setUp(self):
        self.llm = make_llm()

    # ------------------------------------------------------------------
    # Basic message conversion
    # ------------------------------------------------------------------

    def test_system_message_becomes_developer_role(self):
        messages = [SystemPromptMessage(content="You are helpful.")]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "developer")
        self.assertEqual(result[0]["content"], "You are helpful.")

    def test_system_text_content_item_becomes_input_text(self):
        """System prompt multimodal text should use Responses API input_text."""
        messages = [
            SystemPromptMessage(
                content=[TextPromptMessageContent(data="Context from retrieval")]
            )
        ]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "developer")
        content = result[0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["type"], "input_text")
        self.assertEqual(content[0]["text"], "Context from retrieval")

    def test_user_string_message(self):
        messages = [UserPromptMessage(content="Hello")]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "user")
        self.assertEqual(result[0]["content"], "Hello")

    def test_text_content_item_becomes_input_text(self):
        messages = [
            UserPromptMessage(content=[TextPromptMessageContent(data="User question")])
        ]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)
        self.assertEqual(len(result), 1)
        content = result[0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["type"], "input_text")
        self.assertEqual(content[0]["text"], "User question")

    # ------------------------------------------------------------------
    # Regression: DOCUMENT content type (knowledge retrieval context)
    # ------------------------------------------------------------------

    def test_document_only_message_does_not_produce_empty_content_array(self):
        """
        Regression test for "Bad Request Error, Unsupported data type".

        When Dify passes knowledge retrieval context as DocumentPromptMessageContent,
        and no other content types are present, the old code produced:
            {"role": "user", "content": []}
        which Azure Responses API rejects with "Unsupported data type".

        After the fix, messages with no processable content are either skipped
        or the document is included via input_file.
        """
        doc = DocumentPromptMessageContent(
            url="https://example.com/context.pdf",
            mime_type="application/pdf",
            format="pdf",
        )
        messages = [
            SystemPromptMessage(content="Context from knowledge retrieval."),
            UserPromptMessage(content=[doc]),
        ]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)

        # Must NOT produce {"role": "user", "content": []}
        user_msgs = [m for m in result if isinstance(m, dict) and m.get("role") == "user"]
        for msg in user_msgs:
            content = msg.get("content")
            if isinstance(content, list):
                self.assertNotEqual(
                    content,
                    [],
                    "Empty content array causes 'Unsupported data type' in Azure Responses API",
                )

    def test_document_with_base64_data_is_included(self):
        """DOCUMENT content with base64 data should produce an input_file item."""
        doc = DocumentPromptMessageContent(
            base64_data="SGVsbG8=",
            mime_type="application/pdf",
            format="pdf",
            filename="context.pdf",
        )
        messages = [UserPromptMessage(content=[doc])]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)

        user_msgs = [m for m in result if isinstance(m, dict) and m.get("role") == "user"]
        self.assertGreater(len(user_msgs), 0, "Message with DOCUMENT content should be included")
        content = user_msgs[0]["content"]
        self.assertIsInstance(content, list)
        self.assertGreater(len(content), 0)
        file_items = [c for c in content if c.get("type") == "input_file"]
        self.assertGreater(len(file_items), 0, "DOCUMENT should be converted to input_file")

    def test_document_with_url_is_included(self):
        """DOCUMENT content with URL should produce an input_file item with file_url."""
        doc = DocumentPromptMessageContent(
            url="https://example.com/doc.pdf",
            mime_type="application/pdf",
            format="pdf",
        )
        messages = [UserPromptMessage(content=[doc])]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)

        user_msgs = [m for m in result if isinstance(m, dict) and m.get("role") == "user"]
        self.assertGreater(len(user_msgs), 0)
        content = user_msgs[0]["content"]
        file_items = [c for c in content if c.get("type") == "input_file"]
        self.assertGreater(len(file_items), 0)
        self.assertEqual(file_items[0].get("file_url"), "https://example.com/doc.pdf")

    def test_mixed_text_and_document_preserves_text(self):
        """Mixed TEXT + DOCUMENT content should keep the text and include the document."""
        doc = DocumentPromptMessageContent(
            url="https://example.com/doc.pdf",
            mime_type="application/pdf",
            format="pdf",
        )
        messages = [
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="User question here"),
                    doc,
                ]
            )
        ]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)

        user_msgs = [m for m in result if isinstance(m, dict) and m.get("role") == "user"]
        self.assertEqual(len(user_msgs), 1)
        content = user_msgs[0]["content"]
        self.assertIsInstance(content, list)

        text_items = [c for c in content if c.get("type") == "input_text"]
        self.assertEqual(len(text_items), 1)
        self.assertEqual(text_items[0]["text"], "User question here")

    def test_image_content_item_becomes_input_image(self):
        """Existing IMAGE handling should still work."""
        img = ImagePromptMessageContent(
            url="https://example.com/image.png",
            mime_type="image/png",
            format="png",
        )
        messages = [UserPromptMessage(content=[img])]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)

        user_msgs = [m for m in result if isinstance(m, dict) and m.get("role") == "user"]
        self.assertEqual(len(user_msgs), 1)
        image_items = [c for c in user_msgs[0]["content"] if c.get("type") == "input_image"]
        self.assertGreater(len(image_items), 0)

    def test_knowledge_retrieval_full_flow(self):
        """
        Simulates the exact scenario reported:
        - SystemPromptMessage with formatted knowledge retrieval context ({{#context#}} rendered)
        - UserPromptMessage with the user's question

        Both messages should appear in the result with non-empty content.
        """
        system_with_context = (
            "You are a helpful assistant.\n\n"
            "Context:\n"
            "[1] Source: knowledge_base\nContent: Some knowledge content...\n\n"
            "[2] Source: knowledge_base\nContent: More knowledge content..."
        )
        messages = [
            SystemPromptMessage(content=system_with_context),
            UserPromptMessage(content="What is X?"),
        ]
        result = self.llm._convert_prompt_messages_to_responses_input(messages)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["role"], "developer")
        self.assertIn("knowledge", result[0]["content"])
        self.assertEqual(result[1]["role"], "user")
        self.assertEqual(result[1]["content"], "What is X?")


if __name__ == "__main__":
    unittest.main()
