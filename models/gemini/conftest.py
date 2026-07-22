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
