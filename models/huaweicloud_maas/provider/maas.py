import logging
from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class HuaweiCloudMaasProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        pass
