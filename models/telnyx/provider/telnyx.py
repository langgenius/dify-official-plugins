import logging
from collections.abc import Mapping

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class TelnyxProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """Validate Telnyx provider credentials with a cheap embeddings request."""
        try:
            model_instance = self.get_model_instance(ModelType.TEXT_EMBEDDING)
            validate_model = credentials.get("validate_model") or "thenlper/gte-large"
            model_instance.validate_credentials(model=validate_model, credentials=dict(credentials))
        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            logger.exception("Telnyx credentials validate failed")
            raise CredentialsValidateFailedError(str(ex)) from ex
