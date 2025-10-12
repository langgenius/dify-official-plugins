from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from e2b_code_interpreter import Sandbox


class E2bProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            api_key = credentials.get("api_key")
            domain = credentials.get("domain")
            sandbox_args = {"api_key": api_key}
            if domain:
                sandbox_args["domain"] = domain

            sbx = Sandbox(**sandbox_args)
            running_sandboxes = sbx.list(**sandbox_args)

            sbx.kill()

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
