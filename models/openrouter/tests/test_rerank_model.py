from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests

from dify_plugin.entities.model import FetchFrom, ModelPropertyKey, ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.rerank.rerank import OpenRouterRerankModel


class TestOpenRouterRerankModel(unittest.TestCase):
    def setUp(self) -> None:
        self.rerank = OpenRouterRerankModel(model_schemas=[])

    @patch("models.rerank.rerank.requests.post")
    def test_invoke_calls_openrouter_and_filters_by_score(self, mock_post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "model": "cohere/rerank-v3.5",
            "results": [
                {"index": 1, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.25},
            ],
        }
        mock_post.return_value = response

        result = self.rerank._invoke(
            model="cohere/rerank-v3.5",
            credentials={"api_key": "test-key"},
            query="capital",
            docs=["Carson City", "Washington, D.C."],
            score_threshold=0.5,
            top_n=2,
        )

        mock_post.assert_called_once_with(
            "https://openrouter.ai/api/v1/rerank",
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://dify.ai/",
                "X-Title": "Dify",
            },
            json={
                "model": "cohere/rerank-v3.5",
                "query": "capital",
                "documents": ["Carson City", "Washington, D.C."],
                "top_n": 2,
            },
            timeout=(10, 300),
        )
        self.assertEqual(result.model, "cohere/rerank-v3.5")
        self.assertEqual(len(result.docs), 1)
        self.assertEqual(result.docs[0].index, 1)
        self.assertEqual(result.docs[0].text, "Washington, D.C.")
        self.assertEqual(result.docs[0].score, 0.95)

    @patch("models.rerank.rerank.requests.post")
    def test_invoke_normalizes_custom_endpoint_and_omits_top_n(self, mock_post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"results": []}
        mock_post.return_value = response

        self.rerank._invoke(
            model="custom/reranker",
            credentials={
                "api_key": "test-key",
                "endpoint_url": " https://openrouter.example.com/api/v1/ ",
            },
            query="query",
            docs=["document"],
        )

        call = mock_post.call_args
        self.assertEqual(call.args[0], "https://openrouter.example.com/api/v1/rerank")
        self.assertNotIn("top_n", call.kwargs["json"])

    @patch("models.rerank.rerank.requests.post")
    def test_empty_documents_do_not_call_api(self, mock_post: Mock) -> None:
        result = self.rerank._invoke(
            model="cohere/rerank-v3.5", credentials={}, query="query", docs=[]
        )

        self.assertEqual(result.docs, [])
        mock_post.assert_not_called()

    @patch("models.rerank.rerank.requests.post")
    def test_invalid_result_index_is_server_error(self, mock_post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"results": [{"index": 2, "relevance_score": 0.9}]}
        mock_post.return_value = response

        with self.assertRaises(InvokeServerUnavailableError):
            self.rerank._invoke(
                model="cohere/rerank-v3.5",
                credentials={"api_key": "test-key"},
                query="query",
                docs=["only document"],
            )

    @patch("models.rerank.rerank.requests.post")
    def test_http_status_errors_are_mapped(self, mock_post: Mock) -> None:
        cases = [
            (400, InvokeBadRequestError),
            (401, InvokeAuthorizationError),
            (403, InvokeAuthorizationError),
            (429, InvokeRateLimitError),
            (500, InvokeServerUnavailableError),
        ]

        for status_code, expected_error in cases:
            with self.subTest(status_code=status_code):
                response = requests.Response()
                response.status_code = status_code
                response.url = "https://openrouter.ai/api/v1/rerank"
                mock_post.return_value = response

                with self.assertRaises(expected_error):
                    self.rerank._invoke(
                        model="cohere/rerank-v3.5",
                        credentials={"api_key": "test-key"},
                        query="query",
                        docs=["document"],
                    )

    @patch("models.rerank.rerank.requests.post")
    def test_timeout_is_connection_error(self, mock_post: Mock) -> None:
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        with self.assertRaises(InvokeConnectionError):
            self.rerank.invoke(
                model="cohere/rerank-v3.5",
                credentials={"api_key": "test-key"},
                query="query",
                docs=["document"],
            )

    @patch.object(OpenRouterRerankModel, "_invoke")
    def test_validate_credentials_wraps_errors(self, mock_invoke: Mock) -> None:
        mock_invoke.side_effect = InvokeAuthorizationError("bad key")

        with self.assertRaises(CredentialsValidateFailedError):
            self.rerank.validate_credentials("cohere/rerank-v3.5", {"api_key": "bad-key"})

    def test_customizable_model_schema(self) -> None:
        schema = self.rerank.get_customizable_model_schema(
            "custom/reranker", {"context_size": "8192"}
        )

        self.assertEqual(schema.model, "custom/reranker")
        self.assertEqual(schema.model_type, ModelType.RERANK)
        self.assertEqual(schema.fetch_from, FetchFrom.CUSTOMIZABLE_MODEL)
        self.assertEqual(schema.model_properties[ModelPropertyKey.CONTEXT_SIZE], 8192)


if __name__ == "__main__":
    unittest.main()
