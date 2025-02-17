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
        
        market_type = tool_parameters.get("market_type", "spot")
        markets = exchange.fetch_markets()
        
        # filter markets by market_type
        filtered_markets = [
            market['symbol'] 
            for market in markets 
            if market['type'] == market_type
        ]

        yield self.create_json_message({
            "data": filtered_markets
        })
