"""Regression tests for issue #3470.

Lemonade embedding and rerank models could not be added: their
``validate_credentials`` methods called the shared
``validate_lemonade_credentials(credentials)`` without the ``model`` argument,
so the validator's ``if not model: raise CredentialsValidateFailedError(
"Please specify a model name")`` guard fired unconditionally. The LLM, TTS and
speech2text siblings already pass ``model``; these tests pin that the embedding
and rerank call sites do too.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests
from dify_plugin.errors.model import CredentialsValidateFailedError

from models.rerank.rerank import LemonadeRerankModel
from models.text_embedding.text_embedding import LemonadeTextEmbeddingModel


def _healthy_server_responses(model: str):
    """Sequential ``requests.get`` return values: health check, then model list."""
    health = MagicMock()
    health.status_code = 200
    health.json.return_value = {"status": "ok"}

    models = MagicMock()
    models.status_code = 200
    models.json.return_value = {"data": [{"id": model}]}

    return [health, models]


class TestLemonadeCredentialModelArg(unittest.TestCase):
    def setUp(self):
        self.model_name = "Qwen3-Embedding-0.6B-GGUF"
        self.credentials = {"endpoint_url": "http://localhost:8000"}

    @patch("models.llm.llm.requests.get")
    def test_text_embedding_passes_model_and_validates(self, mock_get):
        """Embedding validation reaches the server checks instead of failing on
        the missing-model guard (#3470)."""
        mock_get.side_effect = _healthy_server_responses(self.model_name)

        # Must not raise "Please specify a model name".
        LemonadeTextEmbeddingModel(model_schemas=[]).validate_credentials(
            self.model_name, self.credentials
        )

        # Health endpoint + models endpoint => the model name got past the guard.
        self.assertEqual(mock_get.call_count, 2)

    @patch("models.llm.llm.requests.get")
    def test_rerank_passes_model_and_validates(self, mock_get):
        """Rerank validation reaches the server checks instead of failing on the
        missing-model guard (#3470)."""
        mock_get.side_effect = _healthy_server_responses(self.model_name)

        LemonadeRerankModel(model_schemas=[]).validate_credentials(
            self.model_name, self.credentials
        )

        self.assertEqual(mock_get.call_count, 2)

    @patch("models.llm.llm.requests.get")
    def test_missing_model_name_error_no_longer_raised(self, mock_get):
        """Pin the bug directly: even with an unreachable server, validation must
        not fail with 'Please specify a model name' for embedding or rerank."""
        mock_get.side_effect = requests.exceptions.ConnectionError("server down")

        for model_cls in (LemonadeTextEmbeddingModel, LemonadeRerankModel):
            with self.subTest(model=model_cls.__name__):
                with self.assertRaises(CredentialsValidateFailedError) as ctx:
                    model_cls(model_schemas=[]).validate_credentials(
                        self.model_name, self.credentials
                    )
                self.assertNotIn("Please specify a model name", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
