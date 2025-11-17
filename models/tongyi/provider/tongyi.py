import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class TongyiProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials

        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            model_obj = self.get_model_instance(ModelType.LLM)
            # If the returned object is a class instead of an instance, instantiate it and pass in the model_schemas from the provider schema
            if isinstance(model_obj, type):
                model_instance = model_obj(model_schemas=self.provider_schema.models)
            else:
                model_instance = model_obj
            model_instance.validate_credentials(model="qwen-flash", credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex
