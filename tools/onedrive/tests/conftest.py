import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


@pytest.fixture(autouse=True)
def _clear_token_cache():
    from tools import graph_client

    graph_client._token_cache.clear()
    yield
    graph_client._token_cache.clear()
