import os

from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

# To run: set EUROUTER_API_KEY env var and run pytest


def test_validate_provider_credentials():
    """Test provider credential validation with a real API key."""
    api_key = os.environ.get("EUROUTER_API_KEY")
    if not api_key:
        return

    from provider.eurouter import EUrouterModelProvider

    provider = EUrouterModelProvider()
    provider.validate_provider_credentials(credentials={"eurouter_api_key": api_key})


def test_validate_credentials_with_invalid_key():
    """Test that invalid credentials raise an error."""
    from provider.eurouter import EUrouterModelProvider

    provider = EUrouterModelProvider()
    try:
        provider.validate_provider_credentials(
            credentials={"eurouter_api_key": "invalid-key"}
        )
        assert False, "Should have raised an error"
    except Exception:
        pass
