from collections.abc import Generator
import time
from typing import Any

import ccxt
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class OkxTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        params = {
            "apiKey": self.runtime.credentials.get("api_key"),
            "secret": self.runtime.credentials.get("secret_key"),
            "passphrase": self.runtime.credentials.get("passphrase"),
        }
        exchange = ccxt.okx(params)
        now_timestamp = str(int(time.time() * 1000))
        
        params = {
            "instId": tool_parameters["symbol"],
            "bar": tool_parameters.get("bar", "1m"),
            "after": now_timestamp,
            "limit": str(tool_parameters.get("limit", 100))
        }

        data = exchange.publicGetMarketCandles(params=params).get("data") 

        yield self.create_json_message({
            "data": data
        })
