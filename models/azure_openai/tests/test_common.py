import unittest
from unittest.mock import MagicMock, patch

from models.common import _CommonAzureOpenAI, _client_cache
from models.constants import AZURE_OPENAI_API_VERSION


class CommonAzureOpenAITestCase(unittest.TestCase):
    def setUp(self):
        _client_cache.clear()

    def test_non_v1_endpoint_keeps_api_version(self):
        credentials = {
            "openai_api_base": "https://example-resource.openai.azure.com/",
            "openai_api_key": "test-key",
        }

        kwargs = _CommonAzureOpenAI._to_credential_kwargs(credentials)

        self.assertEqual(
            kwargs["azure_endpoint"],
            "https://example-resource.openai.azure.com/",
        )
        self.assertEqual(kwargs["api_version"], AZURE_OPENAI_API_VERSION)
        self.assertNotIn("base_url", kwargs)

    def test_v1_endpoint_omits_api_version(self):
        credentials = {
            "openai_api_base": "https://example-resource.openai.azure.com/openai/v1/",
            "openai_api_key": "test-key",
            "openai_api_version": "2025-04-01-preview",
        }

        kwargs = _CommonAzureOpenAI._to_credential_kwargs(credentials)

        self.assertEqual(
            kwargs["base_url"],
            "https://example-resource.openai.azure.com/openai/v1/",
        )
        self.assertNotIn("api_version", kwargs)
        self.assertNotIn("azure_endpoint", kwargs)

    @patch("models.common.openai.AzureOpenAI")
    def test_create_client_reuses_cached_client(self, mock_azure_openai):
        mock_client = MagicMock()
        mock_azure_openai.return_value = mock_client
        credentials = {
            "openai_api_base": "https://example-resource.openai.azure.com/",
            "openai_api_key": "test-key",
        }

        first = _CommonAzureOpenAI._create_client(credentials)
        second = _CommonAzureOpenAI._create_client(credentials)

        self.assertIs(first, second)
        mock_azure_openai.assert_called_once()

    @patch("models.common.openai.AzureOpenAI")
    def test_create_client_different_credentials_create_separate_clients(
        self, mock_azure_openai
    ):
        mock_azure_openai.side_effect = [MagicMock(), MagicMock()]
        base_credentials = {
            "openai_api_base": "https://example-resource.openai.azure.com/",
            "openai_api_key": "test-key",
        }

        first = _CommonAzureOpenAI._create_client(base_credentials)
        second = _CommonAzureOpenAI._create_client(
            {**base_credentials, "openai_api_key": "other-key"}
        )

        self.assertIsNot(first, second)
        self.assertEqual(mock_azure_openai.call_count, 2)

    @patch("models.common.openai.AzureOpenAI")
    def test_create_client_use_cache_false_bypasses_cache(self, mock_azure_openai):
        mock_azure_openai.side_effect = [MagicMock(), MagicMock()]
        credentials = {
            "openai_api_base": "https://example-resource.openai.azure.com/",
            "openai_api_key": "test-key",
        }

        first = _CommonAzureOpenAI._create_client(credentials, use_cache=False)
        second = _CommonAzureOpenAI._create_client(credentials, use_cache=False)

        self.assertIsNot(first, second)
        self.assertEqual(mock_azure_openai.call_count, 2)


if __name__ == "__main__":
    unittest.main()
