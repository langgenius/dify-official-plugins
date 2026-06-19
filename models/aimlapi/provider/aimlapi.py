import logging

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class AimlapiProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        if not credentials or not credentials.get("api_key"):
            raise CredentialsValidateFailedError("API key is required")

        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            model_instance.validate_credentials(
                model="openai/gpt-4o-mini",
                credentials=credentials,
            )
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex
