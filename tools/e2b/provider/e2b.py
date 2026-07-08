from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

try:
    from e2b_sandbox import get_sandbox
except ModuleNotFoundError:
    from tools.e2b.e2b_sandbox import get_sandbox


class E2bProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            api_key = credentials.get("api_key")
            domain = credentials.get("domain")
            sbx = get_sandbox(api_key=api_key, domain=domain, timeout=120)

            sbx.kill()

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
