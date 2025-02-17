from collections.abc import Generator
from typing import Any

import ccxt
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class OkxTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        params = {
            "apiKey": self.runtime.credentials.get("api_key"),
            "secret": self.runtime.credentials.get("secret_key"),
            "password": self.runtime.credentials.get("passphrase"),
        }
        exchange = ccxt.okx(params)
        
        account_type = tool_parameters.get("account_type", "spot")
        
        # get balance
        balance = exchange.fetch_balance({'type': account_type})
        # filter out currencies with zero balance
        non_zero_balances = {}
        for currency in balance['total'].keys():
            if balance['total'][currency] > 0:
                non_zero_balances[currency] = {
                    'free': balance['free'][currency],
                    'used': balance['used'][currency],
                    'total': balance['total'][currency]
                }

        yield self.create_json_message({
            "data": non_zero_balances
        }) 