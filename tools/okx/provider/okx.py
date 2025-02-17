from typing import Any

import ccxt
import ccxt.okx
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class OkxProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            """
            IMPLEMENT YOUR VALIDATION HERE
            """
            params = {
                "apiKey": credentials["api_key"],
                "secret": credentials["secret_key"],
                "password": credentials["passphrase"]
            }
            exchange = ccxt.okx(params)
            return exchange.fetch_balance()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))