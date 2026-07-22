import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]


def pytest_configure() -> None:
    load_dotenv(ROOT / ".env")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    enabled = (
        bool(os.getenv("GEMINI_API_KEY", "").strip())
        and os.getenv("RUN_GEMINI_LIVE") == "1"
    )
    if enabled:
        return

    skipped = pytest.mark.skip(
        reason="live tests require GEMINI_API_KEY and RUN_GEMINI_LIVE=1"
    )
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skipped)
