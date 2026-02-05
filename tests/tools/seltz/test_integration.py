"""
Integration tests for Seltz plugin.

These tests require a valid SELTZ_API_KEY environment variable.
Run with: pytest tests/tools/seltz/test_integration.py -v

To skip in CI when no API key is available, these tests are marked with
pytest.mark.skipif when the environment variable is not set.
"""

import os
import pytest

# Skip all tests in this module if no API key is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("SELTZ_API_KEY"),
    reason="SELTZ_API_KEY environment variable not set",
)


@pytest.fixture(scope="module")
def api_key():
    """Fixture to provide the Seltz API key."""
    return os.environ.get("SELTZ_API_KEY")


def test_seltz_client_search(api_key):
    """Test basic Seltz client search functionality."""
    from seltz import Seltz
    from seltz.types import Includes

    client = Seltz(api_key=api_key)

    response = client.search("Python programming", includes=Includes(max_documents=3))

    assert response is not None
    assert hasattr(response, "documents")
    # We expect at least one result for a common query
    assert len(response.documents) > 0

    # Check document structure
    for doc in response.documents:
        assert hasattr(doc, "url")
        assert hasattr(doc, "content")
        assert doc.url  # URL should not be empty
        assert doc.content  # Content should not be empty


def test_seltz_search_different_query(api_key):
    """Test search with a different query."""
    from seltz import Seltz
    from seltz.types import Includes

    client = Seltz(api_key=api_key)

    response = client.search("climate change solutions", includes=Includes(max_documents=5))

    assert response is not None
    assert hasattr(response, "documents")
    assert len(response.documents) > 0

    # Verify document structure
    doc = response.documents[0]
    assert doc.url
    assert doc.content


def test_seltz_credential_validation(api_key):
    """Test that credential validation works with a valid API key."""
    import sys

    # Add plugin directory to path for imports
    plugin_path = os.path.abspath(os.path.join("tools", "seltz"))
    sys.path.insert(0, plugin_path)

    try:
        from provider.seltz import SeltzProvider

        provider = SeltzProvider()

        # Should not raise with valid credentials
        provider._validate_credentials({"api_key": api_key})
    finally:
        sys.path.remove(plugin_path)
