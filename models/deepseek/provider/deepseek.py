import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class DeepSeekProvider(ModelProvider):
    _PRIMARY_VALIDATION_MODEL = "deepseek-v4-flash"
    _FALLBACK_VALIDATION_MODEL = "deepseek-chat"

    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            try:
                model_instance.validate_credentials(model=self._PRIMARY_VALIDATION_MODEL, credentials=credentials)
            except CredentialsValidateFailedError as ex:
                if not self._should_fallback_to_legacy_model(ex):
                    raise ex
                model_instance.validate_credentials(model=self._FALLBACK_VALIDATION_MODEL, credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex

    @staticmethod
    def _should_fallback_to_legacy_model(error: CredentialsValidateFailedError) -> bool:
        error_message = str(error).lower()
        fallback_signals = (
            "model",
            "not exist",
        )
        return all(signal in error_message for signal in fallback_signals)
