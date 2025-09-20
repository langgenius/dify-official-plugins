from typing import Any

from dify_plugin import ToolProvider


class JiandaoyunProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if credentials.get("jiandaoyun_api_key") is None:
            raise ValueError("jiandaoyun_api_key is required in credentials")
        pass
