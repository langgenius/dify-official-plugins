from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from . import _client

WEI_PER_ETHER = 10**18


class PocketBalanceTool(Tool):
    """Get an address balance on a chain through Pocket Network's free public RPC."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        chain = tool_parameters.get("chain", "ethereum") or "ethereum"
        address = tool_parameters.get("address", "")
        if not address:
            yield self.create_text_message("Please input an address.")
            return

        try:
            client = _client.PocketRPCClient()
            balance_wei = client.balance(chain, address)
            chain_id = client.chain_id(chain)
        except Exception as e:
            yield self.create_text_message(f"Error getting the balance: {str(e)}")
            return

        symbol = _client.NATIVE_SYMBOL[chain]
        balance_native = balance_wei / WEI_PER_ETHER
        result = {
            "chain": chain,
            "chain_id": chain_id,
            "address": address,
            "balance_wei": balance_wei,
            "balance_wei_hex": hex(balance_wei),
            "balance_native": balance_native,
            "native_symbol": symbol,
        }
        yield self.create_json_message(result)
        yield self.create_text_message(
            f"The balance of {address} on {chain}, fetched live through Pocket "
            f"Network, is {balance_native} {symbol} ({balance_wei} wei)."
        )
