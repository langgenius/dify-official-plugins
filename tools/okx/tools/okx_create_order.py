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
        
        try:
            # get params
            market_type = tool_parameters.get("market_type", "spot")
            symbol = tool_parameters["symbol"]
            side = tool_parameters["side"]
            order_type = tool_parameters["order_type"]
            amount = float(tool_parameters["amount"])
            price = float(tool_parameters.get("price", 0)) if tool_parameters.get("price") else None
            
            # get market info
            market = exchange.load_markets()
            if symbol not in market:
                raise ValueError(f"Invalid symbol: {symbol}")
            
            market_info = market[symbol]
            min_amount = market_info['limits']['amount']['min']
            
            # check min amount
            if amount < min_amount:
                raise ValueError(f"Order amount ({amount}) is less than minimum required amount ({min_amount})")
            
            # build order params
            order_params = {
                'type': market_type,  # spot/margin/futures/swap
            }
            
            # create order
            if order_type == 'market':
                order = exchange.create_order(
                    symbol=symbol,
                    type=order_type,
                    side=side,
                    amount=amount,
                    params=order_params
                )
            else:  # limit order
                if not price:
                    raise ValueError("Price is required for limit orders")
                order = exchange.create_order(
                    symbol=symbol,
                    type=order_type,
                    side=side,
                    amount=amount,
                    price=price,
                    params=order_params
                )
            
            yield self.create_json_message({
                "data": {
                    "order_id": order['id'],
                    "status": order['status'],
                    "filled": order.get('filled', 0),
                    "remaining": order.get('remaining', amount),
                    "average": order.get('average'),
                    "cost": order.get('cost'),
                    "min_amount": min_amount,
                }
            })
            
        except Exception as e:
            yield self.create_json_message({
                "error": str(e)
            }) 