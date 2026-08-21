import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from models.llm import llm as gemini_llm
from models.text_embedding.text_embedding import _genai_emb_client_cache


ROOT = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def _clear_genai_client_caches():
    """Isolate the plugin's module-level genai.Client caches between tests.

    The plugin reuses one genai.Client per credential for connection-pool
    performance (see models/llm/llm.py and models/text_embedding/
    text_embedding.py). Tests that patch ``genai.Client`` expect their freshly
    configured mock to be the one in use, so the caches must be empty before
    and after every test.
    """
    gemini_llm._genai_client_cache.clear()
    _genai_emb_client_cache.clear()
    yield
    gemini_llm._genai_client_cache.clear()
    _genai_emb_client_cache.clear()


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
