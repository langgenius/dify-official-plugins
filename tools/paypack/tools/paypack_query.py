import json
import os
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class PaypackQueryTool(Tool):

    def _invoke(
        self,
        tool_parameters: Dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            trade_no = tool_parameters.get("trade_no", "")
            currency = (tool_parameters.get("currency") or "CNY").upper()

            if not trade_no:
                yield self.create_text_message("Missing trade number / order ID")
                return

            credentials = self.runtime.credentials or {}

            if currency == "CNY":
                yield from self._query_alipay(trade_no, credentials)
            else:
                yield from self._query_crypto(trade_no, currency, credentials)
        except Exception as e:
            yield self.create_text_message(f"Query failed: {str(e)}")

    def _query_alipay(
        self, trade_no: str, creds: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        from paypack.signer.alipay import AlipaySigner

        app_id = creds.get("app_id")
        private_key = creds.get("private_key")
        alipay_public_key = creds.get("alipay_public_key")
        sandbox = str(creds.get("sandbox", "true")).lower() == "true"

        if private_key and "BEGIN" in private_key:
            signer = AlipaySigner(
                app_id=app_id, private_key=private_key,
                alipay_public_key=alipay_public_key, sandbox=sandbox,
            )
        else:
            signer = AlipaySigner(
                app_id=app_id, private_key_path=private_key,
                alipay_public_key=alipay_public_key, sandbox=sandbox,
            )

        result = signer.query_payment(trade_no)
        resp = result.get("alipay_trade_query_response", result)
        yield self.create_text_message(json.dumps({
            "trade_no": trade_no,
            "code": resp.get("code"),
            "message": resp.get("msg", resp.get("sub_msg", "")),
            "trade_status": resp.get("trade_status", "unknown"),
            "total_amount": resp.get("total_amount", ""),
            "buyer_logon_id": resp.get("buyer_logon_id", ""),
            "gmt_payment": resp.get("send_pay_date", ""),
        }, ensure_ascii=False, indent=2))

    def _query_crypto(
        self, tx_hash: str, currency: str, creds: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        from paypack import AgentPay

        private_key = creds.get("private_key") or os.getenv("PRIVATE_KEY")
        network = creds.get("network", "base-sepolia")

        pay = AgentPay(
            wallet_config={"private_key": private_key},
            network=network, broadcast=False,
        )

        try:
            receipt = pay.w3.eth.get_transaction_receipt(tx_hash)
            yield self.create_text_message(json.dumps({
                "tx_hash": tx_hash,
                "block_number": receipt.get("blockNumber"),
                "status": "success" if receipt.get("status") == 1 else "failed",
                "gas_used": receipt.get("gasUsed"),
            }, ensure_ascii=False, indent=2))
        except Exception:
            yield self.create_text_message(json.dumps({
                "tx_hash": tx_hash,
                "status": "pending_or_not_found",
                "message": "Transaction pending or not found",
            }, ensure_ascii=False, indent=2))
