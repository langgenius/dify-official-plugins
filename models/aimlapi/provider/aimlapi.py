import logging
from collections.abc import Mapping

from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class AIMLAPIProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """
        Validate AI/ML API provider credentials.

        AI/ML API uses bearer-token auth against the OpenAI-compatible
        endpoint at https://api.aimlapi.com/v1. The model layer performs
        per-model credential validation, so the provider-level check is
        intentionally a no-op.
        """
        pass