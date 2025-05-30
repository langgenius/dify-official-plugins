import logging
from collections.abc import Mapping

from dify_plugin import ModelProvider
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError

logger = logging.getLogger(__name__)


class BaiduQianfanModelProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        if credentials.get("api_key", None) is None or len(credentials["api_key"]) == 0:
            raise CredentialsValidateFailedError()

