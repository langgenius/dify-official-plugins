from typing import Any
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.ip_lookup import Ip2GeoLookupTool
from dify_plugin import ToolProvider


class Ip2GeoProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in Ip2GeoLookupTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={"ip_address": "8.8.8.8"}
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
