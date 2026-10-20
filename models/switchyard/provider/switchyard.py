from collections.abc import Mapping

from dify_plugin import ModelProvider


class SwitchyardModelProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """Switchyard has no provider-level credentials; each route validates its own upstreams."""
