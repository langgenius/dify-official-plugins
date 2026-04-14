import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from dify_plugin import OAICompatEmbeddingModel, OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMMode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.llm.llm import OpenRouterLargeLanguageModel
from models.text_embedding.text_embedding import OpenRouterTextEmbeddingModel


class TestOpenRouterEndpointUrlConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = OpenRouterLargeLanguageModel(model_schemas=[])
        self.embedding = OpenRouterTextEmbeddingModel(model_schemas=[])

    @patch.object(OpenRouterLargeLanguageModel, "get_model_schema", return_value=None)
    @patch.object(
        OpenRouterLargeLanguageModel, "get_model_mode", return_value=LLMMode.CHAT
    )
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_llm_validate_credentials_defaults_endpoint_url(
        self,
        mock_super_validate,
        _mock_get_model_mode,
        _mock_get_model_schema,
    ) -> None:
        credentials = {"api_key": "test-key"}

        self.llm.validate_credentials("openrouter/auto", credentials)

        self.assertEqual(credentials["endpoint_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(credentials["mode"], LLMMode.CHAT.value)
        self.assertEqual(
            credentials["extra_headers"],
            {"HTTP-Referer": "https://dify.ai/", "X-Title": "Dify"},
        )
        mock_super_validate.assert_called_once_with("openrouter/auto", credentials)

    @patch.object(OpenRouterLargeLanguageModel, "get_model_schema", return_value=None)
    @patch.object(
        OpenRouterLargeLanguageModel, "get_model_mode", return_value=LLMMode.CHAT
    )
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_llm_validate_credentials_normalizes_custom_endpoint_url(
        self,
        mock_super_validate,
        _mock_get_model_mode,
        _mock_get_model_schema,
    ) -> None:
        credentials = {
            "api_key": "test-key",
            "endpoint_url": " https://openrouter.example.com/api/v1/ ",
        }

        self.llm.validate_credentials("openrouter/auto", credentials)

        self.assertEqual(
            credentials["endpoint_url"], "https://openrouter.example.com/api/v1"
        )
        self.assertEqual(
            credentials["extra_headers"],
            {"HTTP-Referer": "https://dify.ai/", "X-Title": "Dify"},
        )
        mock_super_validate.assert_called_once_with("openrouter/auto", credentials)

    @patch.object(OpenRouterLargeLanguageModel, "get_model_schema", return_value=None)
    @patch.object(
        OpenRouterLargeLanguageModel, "get_model_mode", return_value=LLMMode.CHAT
    )
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_llm_validate_credentials_defaults_blank_endpoint_url(
        self,
        mock_super_validate,
        _mock_get_model_mode,
        _mock_get_model_schema,
    ) -> None:
        credentials = {"api_key": "test-key", "endpoint_url": "   "}

        self.llm.validate_credentials("openrouter/auto", credentials)

        self.assertEqual(credentials["endpoint_url"], "https://openrouter.ai/api/v1")
        mock_super_validate.assert_called_once_with("openrouter/auto", credentials)

    @patch.object(OAICompatEmbeddingModel, "validate_credentials")
    def test_embedding_validate_credentials_defaults_endpoint_url(
        self,
        mock_super_validate,
    ) -> None:
        credentials = {"api_key": "test-key"}

        self.embedding.validate_credentials("text-embedding-3-small", credentials)

        self.assertEqual(credentials["endpoint_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(
            credentials["extra_headers"],
            {"HTTP-Referer": "https://dify.ai/", "X-Title": "Dify"},
        )
        mock_super_validate.assert_called_once_with(
            "text-embedding-3-small", credentials
        )

    @patch.object(OAICompatEmbeddingModel, "validate_credentials")
    def test_embedding_validate_credentials_defaults_blank_endpoint_url(
        self,
        mock_super_validate,
    ) -> None:
        credentials = {"api_key": "test-key", "endpoint_url": "   "}

        self.embedding.validate_credentials("text-embedding-3-small", credentials)

        self.assertEqual(credentials["endpoint_url"], "https://openrouter.ai/api/v1")
        mock_super_validate.assert_called_once_with(
            "text-embedding-3-small", credentials
        )

    @patch.object(OAICompatEmbeddingModel, "validate_credentials")
    def test_embedding_validate_credentials_normalizes_custom_endpoint_url(
        self,
        mock_super_validate,
    ) -> None:
        credentials = {
            "api_key": "test-key",
            "endpoint_url": " https://openrouter.example.com/api/v1/ ",
        }

        self.embedding.validate_credentials("text-embedding-3-small", credentials)

        self.assertEqual(
            credentials["endpoint_url"], "https://openrouter.example.com/api/v1"
        )
        self.assertEqual(
            credentials["extra_headers"],
            {"HTTP-Referer": "https://dify.ai/", "X-Title": "Dify"},
        )
        mock_super_validate.assert_called_once_with(
            "text-embedding-3-small", credentials
        )


if __name__ == "__main__":
    unittest.main()
