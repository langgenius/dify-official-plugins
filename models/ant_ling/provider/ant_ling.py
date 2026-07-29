import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class AntLingModelProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials by delegating to the LLM model instance.
        """
        try:
            validate_model = (credentials.get("validate_model") or "").strip() or "Ling-3.0-flash"
            model_instance = self.get_model_instance(ModelType.LLM)
            model_instance.validate_credentials(model=validate_model, credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex
