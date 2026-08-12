import logging

from collections.abc import Mapping

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class GandrProvider(ModelProvider):
    """Provider-level credential validation for Gandr TTS.

    The actual key check is a single tiny synthesis against the model, so
    provider and model credential paths share the same implementation.
    """

    def validate_provider_credentials(self, credentials: Mapping) -> None:
        try:
            model_instance = self.get_model_instance(ModelType.TTS)
            model_instance.validate_credentials(
                model="", credentials=credentials
            )
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex