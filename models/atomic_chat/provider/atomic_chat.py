import logging
from collections.abc import Mapping

from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class AtomicChatProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        pass
