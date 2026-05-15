"""L2 offline tests: endpoint URL normalization + credential injection.

Adapted from openrouter's test_endpoint_url_config.py. No embedding tests
since OrcaRouter v1 ships LLM only. No HTTP-Referer/X-Title assertions
since those are OpenRouter-specific telemetry.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from dify_plugin import (
    OAICompatEmbeddingModel,
    OAICompatLargeLanguageModel,
    OAICompatText2SpeechModel,
)
from dify_plugin.entities.model.llm import LLMMode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models._endpoint_utils import DEFAULT_ENDPOINT_URL, normalize_endpoint_url
from models.llm.llm import OrcaRouterLargeLanguageModel
from models.text_embedding.text_embedding import OrcaRouterTextEmbeddingModel
from models.tts.tts import OrcaRouterText2SpeechModel


class TestNormalizeEndpointUrl(unittest.TestCase):
    """Unit tests for the normalize_endpoint_url helper."""

    def test_default_when_key_missing(self) -> None:
        self.assertEqual(normalize_endpoint_url({}), DEFAULT_ENDPOINT_URL)
        self.assertEqual(DEFAULT_ENDPOINT_URL, "https://api.orcarouter.ai/v1")

    def test_default_when_blank(self) -> None:
        self.assertEqual(
            normalize_endpoint_url({"endpoint_url": "   "}), DEFAULT_ENDPOINT_URL
        )
        self.assertEqual(
            normalize_endpoint_url({"endpoint_url": ""}), DEFAULT_ENDPOINT_URL
        )

    def test_default_when_none(self) -> None:
        self.assertEqual(
            normalize_endpoint_url({"endpoint_url": None}), DEFAULT_ENDPOINT_URL
        )

    def test_strips_whitespace_and_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_endpoint_url({"endpoint_url": " https://example.com/api/v1/ "}),
            "https://example.com/api/v1",
        )

    def test_preserves_clean_url(self) -> None:
        url = "https://custom.example.com/v1"
        self.assertEqual(normalize_endpoint_url({"endpoint_url": url}), url)


class TestOrcaRouterEndpointUrlConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = OrcaRouterLargeLanguageModel(model_schemas=[])

    @patch.object(OrcaRouterLargeLanguageModel, "get_model_schema", return_value=None)
    @patch.object(OrcaRouterLargeLanguageModel, "get_model_mode", return_value=LLMMode.CHAT)
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_llm_validate_credentials_defaults_endpoint_url(
        self, mock_super_validate, _mock_get_mode, _mock_get_schema
    ) -> None:
        credentials = {"api_key": "test-key"}
        self.llm.validate_credentials("orcarouter/auto", credentials)

        self.assertEqual(credentials["endpoint_url"], "https://api.orcarouter.ai/v1")
        self.assertEqual(credentials["mode"], LLMMode.CHAT.value)
        # OrcaRouter does NOT inject HTTP-Referer/X-Title (that's OpenRouter telemetry)
        self.assertNotIn("extra_headers", credentials)
        mock_super_validate.assert_called_once_with("orcarouter/auto", credentials)

    @patch.object(OrcaRouterLargeLanguageModel, "get_model_schema", return_value=None)
    @patch.object(OrcaRouterLargeLanguageModel, "get_model_mode", return_value=LLMMode.CHAT)
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_llm_validate_credentials_normalizes_custom_endpoint(
        self, mock_super_validate, _mock_get_mode, _mock_get_schema
    ) -> None:
        credentials = {
            "api_key": "test-key",
            "endpoint_url": " https://orcarouter.example.com/api/v1/ ",
        }
        self.llm.validate_credentials("orcarouter/auto", credentials)
        self.assertEqual(
            credentials["endpoint_url"], "https://orcarouter.example.com/api/v1"
        )
        mock_super_validate.assert_called_once_with("orcarouter/auto", credentials)

    @patch.object(OrcaRouterLargeLanguageModel, "get_model_schema", return_value=None)
    @patch.object(OrcaRouterLargeLanguageModel, "get_model_mode", return_value=LLMMode.CHAT)
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_llm_validate_credentials_blank_falls_back_to_default(
        self, mock_super_validate, _mock_get_mode, _mock_get_schema
    ) -> None:
        credentials = {"api_key": "test-key", "endpoint_url": "   "}
        self.llm.validate_credentials("orcarouter/auto", credentials)
        self.assertEqual(credentials["endpoint_url"], "https://api.orcarouter.ai/v1")
        mock_super_validate.assert_called_once_with("orcarouter/auto", credentials)


class TestEmbeddingEndpointUrlConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.embedding = OrcaRouterTextEmbeddingModel(model_schemas=[])

    @patch.object(OAICompatEmbeddingModel, "validate_credentials")
    def test_embedding_validate_credentials_defaults_endpoint(
        self, mock_super_validate
    ) -> None:
        credentials = {"api_key": "test-key"}
        self.embedding.validate_credentials("openai/text-embedding-3-small", credentials)
        self.assertEqual(credentials["endpoint_url"], "https://api.orcarouter.ai/v1")
        # No HTTP-Referer / X-Title (OpenRouter telemetry); we don't add them
        self.assertNotIn("extra_headers", credentials)
        mock_super_validate.assert_called_once_with(
            "openai/text-embedding-3-small", credentials
        )

    @patch.object(OAICompatEmbeddingModel, "validate_credentials")
    def test_embedding_validate_credentials_normalizes_custom_endpoint(
        self, mock_super_validate
    ) -> None:
        credentials = {
            "api_key": "test-key",
            "endpoint_url": " https://orcarouter.example.com/api/v1/ ",
        }
        self.embedding.validate_credentials("openai/text-embedding-3-small", credentials)
        self.assertEqual(
            credentials["endpoint_url"], "https://orcarouter.example.com/api/v1"
        )

    @patch.object(OAICompatEmbeddingModel, "validate_credentials")
    def test_embedding_blank_endpoint_falls_back(self, mock_super_validate) -> None:
        credentials = {"api_key": "test-key", "endpoint_url": "  "}
        self.embedding.validate_credentials("openai/text-embedding-3-small", credentials)
        self.assertEqual(credentials["endpoint_url"], "https://api.orcarouter.ai/v1")


class TestTTSEndpointUrlConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.tts = OrcaRouterText2SpeechModel(model_schemas=[])

    @patch.object(OAICompatText2SpeechModel, "validate_credentials")
    def test_tts_validate_credentials_defaults_endpoint(
        self, mock_super_validate
    ) -> None:
        credentials = {"api_key": "test-key"}
        self.tts.validate_credentials("openai/tts-1", credentials)
        self.assertEqual(credentials["endpoint_url"], "https://api.orcarouter.ai/v1")
        self.assertNotIn("extra_headers", credentials)
        mock_super_validate.assert_called_once_with("openai/tts-1", credentials)

    @patch.object(OAICompatText2SpeechModel, "validate_credentials")
    def test_tts_validate_credentials_normalizes_custom_endpoint(
        self, mock_super_validate
    ) -> None:
        credentials = {
            "api_key": "test-key",
            "endpoint_url": " https://orcarouter.example.com/api/v1/ ",
        }
        self.tts.validate_credentials("openai/tts-1", credentials)
        self.assertEqual(
            credentials["endpoint_url"], "https://orcarouter.example.com/api/v1"
        )


if __name__ == "__main__":
    unittest.main()
