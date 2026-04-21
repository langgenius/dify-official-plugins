import logging

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class HpcAIProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            model_instance.validate_credentials(
                model="minimax/minimax-m2.5", credentials=credentials
            )
        except CredentialsValidateFailedError:
            raise
        except Exception:
            logger.exception(
                "%s credentials validate failed", self.get_provider_schema().provider
            )
            raise
