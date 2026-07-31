import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)

# Sentinel model used for credential validation. Picked as the earliest Kimi
# K-series chat model in the plugin's predefined catalog so it has broad
# availability across Moonshot API key tiers — a key valid for any K-series
# model will pass validation against it. Moonshot API keys that only cover
# the older moonshot-v1-* series (which the previous default used to fail on)
# are no longer impacted: callers can override the sentinel by passing
# `validate_model` in the credentials dict.
DEFAULT_VALIDATE_MODEL = "kimi-k2-0711-preview"


class MoonshotProvider(ModelProvider):
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
