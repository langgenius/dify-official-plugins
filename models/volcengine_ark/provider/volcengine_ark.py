import logging

from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class VolcengineArkProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        # Validation happens in model impl (validate_credentials)
        return
