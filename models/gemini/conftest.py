import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent


def pytest_configure() -> None:
    load_dotenv(ROOT / ".env")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.getenv("GEMINI_API_KEY", "").strip():
        return

    skipped = pytest.mark.skip(reason="live tests require GEMINI_API_KEY")
    for item in items:
        in_gemini = Path(str(item.path)).resolve().is_relative_to(ROOT)
        if in_gemini and item.get_closest_marker("live") is not None:
            item.add_marker(skipped)


@pytest.fixture(autouse=True)
def _reset_genai_client_caches():
    """Reset the module-level ``genai.Client`` caches (added for issue #3333)
    before and after every test.

    ``models.llm.llm._genai_client_cache`` and
    ``models.text_embedding.text_embedding._genai_emb_client_cache`` are
    process-wide module-level dicts keyed by API key. Many tests in this
    suite reuse the same placeholder credentials (e.g. ``"fake-key"``,
    ``"test-key"``). Without resetting the caches, a test could silently
    receive a cached client (and its mock) left behind by an earlier,
    unrelated test instead of the one it just patched -- a correctness
    hazard specific to the test suite, not to production use (real
    deployments use real, distinct API keys).
    """
    from models.llm import llm as _llm_module
    from models.text_embedding import text_embedding as _embedding_module

    _llm_module._genai_client_cache.clear()
    _embedding_module._genai_emb_client_cache.clear()
    yield
    _llm_module._genai_client_cache.clear()
    _embedding_module._genai_emb_client_cache.clear()
