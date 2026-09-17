import logging

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class IonetProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            model_instance.validate_credentials(
                model="meta-llama/Llama-3.3-70B-Instruct", credentials=credentials
            )
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(
                "%s credentials validate failed",
                self.get_provider_schema().provider,
            )
            raise ex
