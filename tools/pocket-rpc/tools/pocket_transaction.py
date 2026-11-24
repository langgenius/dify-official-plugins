from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from . import _client


class PocketTransactionTool(Tool):
    """Get a transaction by hash on a chain through Pocket Network's free public RPC."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        chain = tool_parameters.get("chain", "ethereum") or "ethereum"
        tx_hash = tool_parameters.get("tx_hash", "")
        if not tx_hash:
            yield self.create_text_message("Please input a transaction hash.")
            return

        try:
            client = _client.PocketRPCClient()
            tx = client.transaction(chain, tx_hash)
        except Exception as e:
            yield self.create_text_message(f"Error getting the transaction: {str(e)}")
            return

        if tx is None:
            yield self.create_text_message(
                f"No transaction with hash {tx_hash} exists on {chain}."
            )
            return

        try:
            chain_id = client.chain_id(chain)
        except Exception as e:
            yield self.create_text_message(f"Error getting the transaction: {str(e)}")
            return

        result = {
            "chain": chain,
            "chain_id": chain_id,
            "transaction": tx,
        }
        yield self.create_json_message(result)
        block_number = tx.get("blockNumber")
        block_text = (
            f" in block {int(block_number, 16)}" if block_number else ""
        )
        yield self.create_text_message(
            f"Transaction {tx_hash} on {chain}, fetched live through Pocket "
            f"Network: from {tx.get('from')} to {tx.get('to')}, value "
            f"{int(tx.get('value', '0x0'), 16)} wei{block_text}."
        )
