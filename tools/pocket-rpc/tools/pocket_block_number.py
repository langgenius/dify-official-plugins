from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from . import _client


class PocketBlockNumberTool(Tool):
    """Get the current block number of a chain through Pocket Network's free public RPC."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        chain = tool_parameters.get("chain", "ethereum") or "ethereum"
        try:
            client = _client.PocketRPCClient()
            block_number = client.block_number(chain)
            chain_id = client.chain_id(chain)
        except Exception as e:
            yield self.create_text_message(f"Error getting the block number: {str(e)}")
            return

        result = {
            "chain": chain,
            "chain_id": chain_id,
            "block_number": block_number,
            "block_number_hex": hex(block_number),
        }
        yield self.create_json_message(result)
        yield self.create_text_message(
            f"The current {chain} block number, fetched live through Pocket "
            f"Network, is {block_number} (hex {hex(block_number)})."
        )
