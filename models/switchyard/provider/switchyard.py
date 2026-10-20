from collections.abc import Mapping
from typing import override

from dify_plugin import ModelProvider


class SwitchyardModelProvider(ModelProvider):
    @override
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """Switchyard has no provider-level credentials; each route validates its own upstreams."""
