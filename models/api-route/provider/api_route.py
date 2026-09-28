import logging

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError


logger = logging.getLogger(__name__)


class APIRouteProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        try:
            model = self.get_model_instance(ModelType.LLM)
            model.validate_credentials(model="deepseek-v4-pro", credentials=credentials)
        except CredentialsValidateFailedError:
            raise
        except Exception as exc:
            logger.exception("API Route credentials validation failed")
            raise CredentialsValidateFailedError(str(exc)) from exc
