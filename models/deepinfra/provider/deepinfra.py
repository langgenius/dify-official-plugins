import logging

from dify_plugin import ModelProvider
from dify_plugin.errors.model import CredentialsValidateFailedError
from openai import OpenAI

logger = logging.getLogger(__name__)


class DeepInfraProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            client = OpenAI(
                api_key=credentials["api_key"],
                base_url="https://api.deepinfra.com/v1/openai",
            )
            client.models.list()
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise CredentialsValidateFailedError(str(ex))
