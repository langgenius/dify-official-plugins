import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)

# Sentinel model used for credential validation. Picked as one of the oldest
# Tongyi chat models so it has broad availability across all DashScope
# tiers — a key valid for any Tongyi model will pass validation against it.
# Callers can override the sentinel by passing `validate_model` in the
# credentials dict (e.g. when the key only covers a different model).
DEFAULT_VALIDATE_MODEL = "qwen-turbo"


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
            validate_model = credentials.get("validate_model") or DEFAULT_VALIDATE_MODEL
            model_instance.validate_credentials(
                model=validate_model, credentials=credentials
            )
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(
                f"{self.get_provider_schema().provider} credentials validate failed"
            )
            raise ex
