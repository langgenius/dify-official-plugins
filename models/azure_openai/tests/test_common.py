import unittest

from models.common import _CommonAzureOpenAI
from models.constants import AZURE_OPENAI_API_VERSION


class CommonAzureOpenAITestCase(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
