import logging
import requests
from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class SiliconflowProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            url = "https://api.siliconflow.cn/v1/models"
            headers = {"accept": "application/json", "authorization": f"Bearer {credentials.get('api_key')}"}
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                raise CredentialsValidateFailedError("SiliconFlow API key is invalid")
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex
