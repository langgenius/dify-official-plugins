from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from e2b_code_interpreter import Sandbox


class E2bProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            sbx = Sandbox(api_key=credentials.get("api_key"))

            running_sandboxes = sbx.list(api_key=credentials.get("api_key"))

            sbx.kill()

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
