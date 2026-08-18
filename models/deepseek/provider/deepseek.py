import logging

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class DeepSeekProvider(ModelProvider):
    _VALIDATION_MODEL = "deepseek-v4-flash"

    def validate_provider_credentials(self, credentials: dict) -> None:
        try:
            self.get_model_instance(ModelType.LLM).validate_credentials(
                model=self._VALIDATION_MODEL,
                credentials=credentials,
            )
        except CredentialsValidateFailedError:
            raise
        except Exception:
            logger.exception(
                "%s credentials validate failed",
                self.get_provider_schema().provider,
            )
            raise
