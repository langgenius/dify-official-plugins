import logging
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider
from openai import OpenAI

logger = logging.getLogger(__name__)


class FireworksProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            client = OpenAI(
                api_key=credentials["fireworks_api_key"],
                base_url="https://api.fireworks.ai/inference/v1",
            )
            client.models.list()
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise CredentialsValidateFailedError(str(ex))
