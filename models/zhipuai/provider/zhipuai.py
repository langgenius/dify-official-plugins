import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)

# Sentinel model used for credential validation. Kept as the value the plugin
# has always used, so default behaviour is unchanged for existing users.
# Callers can override the sentinel by passing `validate_model` in the
# credentials dict — needed when `base_url` points at a private or internal
# ZhipuAI-compatible endpoint that hosts different model names.
DEFAULT_VALIDATE_MODEL = "glm-5-turbo"


class ZhipuaiProvider(ModelProvider):
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
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex
