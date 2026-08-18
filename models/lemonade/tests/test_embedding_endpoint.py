"""Regression test for issue #3491.

Lemonade embedding models 404 on `/embeddings` when indexing a document. The
base ``OAICompatEmbeddingModel._invoke`` posts to ``{endpoint_url}/embeddings``,
and the embedding path (unlike the LLM path's ``_add_custom_parameters``) never
appended Lemonade's ``/api/v1`` prefix — so with the placeholder endpoint
``http://127.0.0.1:13305`` the request went to ``.../embeddings`` and 404'd. The
fix normalizes ``endpoint_url`` to include ``/api/v1`` before delegating, so the
request goes to ``.../api/v1/embeddings``.
"""

import contextlib
import unittest
from unittest.mock import MagicMock, patch

from models.text_embedding.text_embedding import LemonadeTextEmbeddingModel

# The base class builds the URL inside this module's `requests`, so patch there.
_REQUESTS_POST = "dify_plugin.interfaces.model.openai_compatible.text_embedding.requests.post"


class TestLemonadeEmbeddingEndpoint(unittest.TestCase):
    def _run_invoke_and_capture_url(self, endpoint_url: str) -> str:
        """Invoke embedding with a mocked HTTP layer; return the POSTed URL."""
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
            "usage": {"total_tokens": 3},
        }

        # Pin the model-property helpers so _invoke reaches the HTTP call without
        # needing a predefined model schema; the endpoint URL is what's under test.
        with (
            patch(_REQUESTS_POST, return_value=resp) as mock_post,
            patch.object(LemonadeTextEmbeddingModel, "_get_context_size", return_value=8192),
            patch.object(LemonadeTextEmbeddingModel, "_get_max_chunks", return_value=1),
        ):
            # Downstream response/usage handling is the SDK's concern, not under
            # test — the URL is captured at the POST regardless of what follows.
            with contextlib.suppress(Exception):
                LemonadeTextEmbeddingModel(model_schemas=[])._invoke(
                    "nomic-embed-text-v1-GGUF",
                    {"endpoint_url": endpoint_url},
                    ["hello world"],
                )
            self.assertTrue(mock_post.called, "embedding must issue an HTTP request")
            call = mock_post.call_args
            return call.args[0] if call.args else call.kwargs["url"]

    def test_embedding_posts_to_api_v1_embeddings(self):
        """With the bare placeholder endpoint, the request must target
        /api/v1/embeddings (not /embeddings) — the #3491 fix."""
        url = self._run_invoke_and_capture_url("http://127.0.0.1:13305")
        self.assertEqual(url, "http://127.0.0.1:13305/api/v1/embeddings")

    def test_embedding_does_not_double_api_v1(self):
        """If the endpoint already includes /api/v1, it must not be duplicated
        (matches the LLM path's guard)."""
        url = self._run_invoke_and_capture_url("http://127.0.0.1:13305/api/v1")
        self.assertEqual(url, "http://127.0.0.1:13305/api/v1/embeddings")


if __name__ == "__main__":
    unittest.main()
