import logging

from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model import ModelProvider

logger = logging.getLogger(__name__)


class PPIOProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)

            # Use `meta-llama/llama-3.1-8b-instruct` model for validate,
            # no matter what model you pass in, text completion model or chat model
            model_instance.validate_credentials(model="meta-llama/llama-3.1-8b-instruct", credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex
