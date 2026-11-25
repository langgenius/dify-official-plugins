import logging

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class OrukProvider(ModelProvider):
    """Dify model provider for Oruk speech-to-text."""

    def validate_provider_credentials(self, credentials: dict) -> None:
        """Validate provider-level credentials by delegating to the speech2text model."""
        try:
            model_instance = self.get_model_instance(ModelType.SPEECH2TEXT)
            model_instance.validate_credentials(model="oruk-fourier-2b", credentials=credentials)
        except CredentialsValidateFailedError:
            raise
        except Exception:
            logger.exception("%s credentials validate failed", self.get_provider_schema().provider)
            raise
