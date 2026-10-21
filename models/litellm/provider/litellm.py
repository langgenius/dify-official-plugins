from collections.abc import Mapping

from dify_plugin import ModelProvider


class LiteLLMProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """Models are configured one by one, so there are no provider-level credentials."""
