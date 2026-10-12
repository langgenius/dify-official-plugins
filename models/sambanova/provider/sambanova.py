import logging
from collections.abc import Mapping

import requests
from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)

MODELS_URL = "https://api.sambanova.ai/v1/models"
DEFAULT_VALIDATION_MODEL = "Meta-Llama-3.3-70B-Instruct"


class SambanovaModelProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            model = self._select_validation_model(
                [m.model for m in model_instance.predefined_models()]
            )
            model_instance.validate_credentials(model=model, credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(
                f"{self.get_provider_schema().provider} credentials validate failed"
            )
            raise ex

    @staticmethod
    def _select_validation_model(predefined: list[str]) -> str:
        """
        Pick a predefined model that SambaCloud currently serves, so that a model
        retired on SambaCloud does not make a valid API key fail validation.
        The model list endpoint does not require authentication.
        """
        try:
            response = requests.get(MODELS_URL, timeout=10)
            response.raise_for_status()
            available = {m["id"] for m in response.json()["data"]}
        except Exception:
            logger.warning(
                "Failed to fetch SambaCloud model list, using %s for validation",
                DEFAULT_VALIDATION_MODEL,
            )
            return DEFAULT_VALIDATION_MODEL

        for model in [DEFAULT_VALIDATION_MODEL, *predefined]:
            if model in available:
                return model
        return DEFAULT_VALIDATION_MODEL
