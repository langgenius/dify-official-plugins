from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils.client import Credentials, MineruError, validate_credentials


class MineruProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            validate_credentials(Credentials.from_mapping(credentials))
        except MineruError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Failed to validate MinerU credentials: {e}") from e
