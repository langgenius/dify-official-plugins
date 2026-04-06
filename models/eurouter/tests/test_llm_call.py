import os

import pytest
from dify_plugin.errors.model import CredentialsValidateFailedError


@pytest.mark.skipif(
    not os.environ.get("EUROUTER_API_KEY"), reason="EUROUTER_API_KEY not set"
)
def test_validate_provider_credentials():
    """Test provider credential validation with a real API key."""
    from provider.eurouter import EUrouterModelProvider

    provider = EUrouterModelProvider()
    provider.validate_provider_credentials(
        credentials={"eurouter_api_key": os.environ["EUROUTER_API_KEY"]}
    )


def test_validate_credentials_with_invalid_key():
    """Test that invalid credentials raise an error."""
    from provider.eurouter import EUrouterModelProvider

    provider = EUrouterModelProvider()
    with pytest.raises(CredentialsValidateFailedError):
        provider.validate_provider_credentials(
            credentials={"eurouter_api_key": "invalid-key"}
        )
