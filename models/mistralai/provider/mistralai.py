import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)

# Sentinel model used for credential validation. Picked as a small, current-generation
# Mistral chat model so it has broad availability across all Mistral key tiers — a key
# valid for any current Mistral model will pass validation against it. The previous
# default (`open-mistral-7b`) is from Mistral's 2023 naming convention and is not in
# the plugin's current predefined catalog; current keys return a 404 on it.
# Callers can override the sentinel by passing `validate_model` in the
# credentials dict (e.g. when the key only covers a different model).
DEFAULT_VALIDATE_MODEL = "mistral-small-latest"


class MistralAIProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
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
