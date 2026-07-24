import logging

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class JalapenoCloudProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials.
        Raises CredentialsValidateFailedError when validation fails.
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            if isinstance(model_instance, type):
                model_instance = model_instance(
                    model_schemas=self.provider_schema.models
                )
            model_instance.validate_credentials(
                model="GLM-5.2",
                credentials=credentials,
            )
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(
                "%s credentials validate failed",
                self.get_provider_schema().provider,
            )
            raise ex
