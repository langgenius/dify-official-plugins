from typing import Any

from tools.telegraph import TelegraphTool
import time

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class TelegraphProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in TelegraphTool.from_credentials(credentials).invoke(
                tool_parameters={
                    "p_title": "My First Page",
                    "p_content": f"""
# Hello World!
This is my first page on Telegraph.

It was created at {time.strftime("%Y-%m-%d %H:%M:%S")}.

---

## Credential Validation Test Passed
                    """,
                    "a_telegraph_access_token": ""
                }
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
