"""Regression tests for ``credentials['extra_headers']`` threading across the
non-LLM modules of the OpenAI-API-compatible provider.

PR #4010 added an ``extra_headers`` model parameter for the LLM module
(``models/llm/llm.py``) that flows into the OAICompat base class's
``_generate`` method via the ``credentials['extra_headers']`` thread.
The four non-LLM modules — text-embedding, rerank, tts, and
speech2text — each build their own local ``headers`` dict and were
not reading ``credentials['extra_headers']`` at all. Setting
``credentials['extra_headers']`` (e.g. from a provider credential
override or a future per-module parameter) silently dropped on those
modules.

This fix adds the same merge in each of the four modules, mirroring
the LLM behaviour. The per-model ``extra_headers`` parameter added by
PR #4010 is still LLM-only (the non-LLM SDK interfaces don't
thread ``model_parameters`` through); this PR closes the credential-
level gap.

Each module is tested via mocking the ``requests.post`` boundary so
no network is required. The captured ``headers`` dict is asserted
to contain the merged extra entries.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# text-embedding
# ---------------------------------------------------------------------------


def test_text_embedding_threads_extra_headers_into_requests_post():
    """``credentials['extra_headers']`` reaches the embeddings POST headers."""
    from models.text_embedding.text_embedding import OpenAITextEmbeddingModel

    llm = OpenAITextEmbeddingModel(model_schemas=[])
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["headers"] = headers
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": [{"embedding": [0.0]}]}
        response.raise_for_status = MagicMock()
        return response

    with patch("models.text_embedding.text_embedding.requests.post", new=fake_post):
        llm._invoke(
            model="text-embedding-3-small",
            credentials={
                "mode": "embedding",
                "endpoint_url": "https://api.example.com/v1",
                "api_key": "test-key",
                "extra_headers": {"x-trace-id": "abc"},
            },
            texts=["ping"],
            user=None,
        )

    assert captured["headers"]["x-trace-id"] == "abc"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["headers"]["Content-Type"] == "application/json"


def test_text_embedding_no_extra_headers_unchanged():
    """Without ``extra_headers`` the headers dict only has Authorization + Content-Type."""
    from models.text_embedding.text_embedding import OpenAITextEmbeddingModel

    llm = OpenAITextEmbeddingModel(model_schemas=[])
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["headers"] = headers
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": [{"embedding": [0.0]}]}
        response.raise_for_status = MagicMock()
        return response

    with patch("models.text_embedding.text_embedding.requests.post", new=fake_post):
        llm._invoke(
            model="text-embedding-3-small",
            credentials={
                "mode": "embedding",
                "endpoint_url": "https://api.example.com/v1",
                "api_key": "test-key",
            },
            texts=["ping"],
            user=None,
        )

    assert "x-trace-id" not in captured["headers"]
    assert "X-Trace-Id" not in captured["headers"]


# ---------------------------------------------------------------------------
# rerank
# ---------------------------------------------------------------------------


def test_rerank_threads_extra_headers_into_requests_post():
    """``credentials['extra_headers']`` reaches the rerank POST headers."""
    from models.rerank.rerank import OpenAIRerankModel

    llm = OpenAIRerankModel(model_schemas=[])
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["headers"] = headers
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.9}]}
        response.raise_for_status = MagicMock()
        return response

    with patch("models.rerank.rerank.requests.post", new=fake_post):
        llm._invoke(
            model="rerank-english-v3.0",
            credentials={
                "mode": "rerank",
                "endpoint_url": "https://api.example.com/v1",
                "api_key": "test-key",
                "extra_headers": {"x-rerank-tenant": "tenant-1"},
            },
            query="what is the capital of France?",
            docs=["Paris is the capital of France."],
            score_threshold=0.0,
            top_n=1,
            user=None,
        )

    assert captured["headers"]["x-rerank-tenant"] == "tenant-1"
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_rerank_no_extra_headers_unchanged():
    """Without ``extra_headers`` the headers dict only has Authorization + Content-Type."""
    from models.rerank.rerank import OpenAIRerankModel

    llm = OpenAIRerankModel(model_schemas=[])
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["headers"] = headers
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.9}]}
        response.raise_for_status = MagicMock()
        return response

    with patch("models.rerank.rerank.requests.post", new=fake_post):
        llm._invoke(
            model="rerank-english-v3.0",
            credentials={
                "mode": "rerank",
                "endpoint_url": "https://api.example.com/v1",
                "api_key": "test-key",
            },
            query="what is the capital of France?",
            docs=["Paris is the capital of France."],
            score_threshold=0.0,
            top_n=1,
            user=None,
        )

    assert "x-rerank-tenant" not in captured["headers"]


# ---------------------------------------------------------------------------
# speech2text
# ---------------------------------------------------------------------------


def test_speech2text_threads_extra_headers_into_requests_post():
    """``credentials['extra_headers']`` reaches the speech2text POST headers."""
    from models.speech2text.speech2text import OpenAISpeech2TextModel

    llm = OpenAISpeech2TextModel(model_schemas=[])
    captured = {}

    def fake_post(url, headers, data, files, timeout):
        captured["headers"] = headers
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"text": "transcribed"}
        return response

    with patch("models.speech2text.speech2text.requests.post", new=fake_post):
        llm._invoke(
            model="whisper-1",
            credentials={
                "endpoint_url": "https://api.example.com/v1/",
                "api_key": "test-key",
                "extra_headers": {"x-trace-id": "abc"},
            },
            file=MagicMock(),
        )

    assert captured["headers"]["x-trace-id"] == "abc"
    assert captured["headers"]["Authorization"] == "Bearer test-key"


# ---------------------------------------------------------------------------
# tts
# ---------------------------------------------------------------------------


def test_tts_threads_extra_headers_into_requests_post():
    """``credentials['extra_headers']`` reaches the BytePlus TTS POST headers.

    The plugin dispatches to ``_invoke_byteplus`` when the
    ``tts_api_format`` credential is ``"byteplus"``; the standard OpenAI
    path delegates to the OAICompat base class (which already threads
    ``credentials['extra_headers']`` via its base implementation). The
    BytePlus path is the one that builds its own local ``headers`` dict
    and was previously dropping ``extra_headers``.
    """
    from models.tts.tts import OpenAIText2SpeechModel

    llm = OpenAIText2SpeechModel(model_schemas=[])
    captured = {}

    def fake_post(url, headers, json, timeout, stream=False):
        captured["headers"] = headers
        response = MagicMock()
        response.status_code = 200
        response.headers = {}
        response.content = b"audio-bytes"
        return response

    with patch("models.tts.tts.requests.post", new=fake_post):
        # OpenAIText2SpeechModel._invoke signature: (model, tenant_id, credentials,
        # content_text, voice, user). ``tts_api_format=byteplus`` routes to
        # ``_invoke_byteplus`` which builds its own headers dict.
        gen = llm._invoke(
            model="tts-1",
            tenant_id="tenant-id",
            credentials={
                "endpoint_url": "https://api.example.com/v1",
                "api_key": "test-key",
                "tts_resource_id": "resource-id",
                "tts_api_format": "byteplus",
                "extra_headers": {"x-trace-id": "abc"},
            },
            content_text="Hello",
            voice="alloy",
            user=None,
        )
        # Force the generator to run by exhausting it.
        list(gen)

    assert captured["headers"]["x-trace-id"] == "abc"
    assert captured["headers"]["x-api-key"] == "test-key"


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------


def test_non_llm_modules_each_merge_extra_headers():
    """Each of the four non-LLM modules reads ``credentials.get('extra_headers')``."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]

    # text_embedding.py should contain an `extra_headers = credentials.get(...)` line.
    te_text = (repo_root / "models" / "text_embedding" / "text_embedding.py").read_text(
        encoding="utf-8"
    )
    assert "extra_headers = credentials.get" in te_text, (
        "text_embedding.py must merge credentials['extra_headers'] into the "
        "outbound headers dict (LLM parity fix)"
    )

    # rerank.py must contain it (twice — text + multimodal paths).
    rerank_text = (repo_root / "models" / "rerank" / "rerank.py").read_text(
        encoding="utf-8"
    )
    assert rerank_text.count("extra_headers = credentials.get") == 2, (
        "rerank.py must merge credentials['extra_headers'] into the outbound "
        "headers dict on BOTH the text path (line ~119) and the multimodal "
        "path (line ~242). Both were previously dropping the headers."
    )

    # speech2text.py and tts.py each have one merge site.
    s2t_text = (repo_root / "models" / "speech2text" / "speech2text.py").read_text(
        encoding="utf-8"
    )
    assert "extra_headers = credentials.get" in s2t_text, (
        "speech2text.py must merge credentials['extra_headers'] into the "
        "outbound headers dict"
    )

    tts_text = (repo_root / "models" / "tts" / "tts.py").read_text(encoding="utf-8")
    assert "extra_headers = credentials.get" in tts_text, (
        "tts.py must merge credentials['extra_headers'] into the outbound "
        "headers dict"
    )