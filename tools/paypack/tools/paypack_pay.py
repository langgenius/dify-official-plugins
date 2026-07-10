import json
import os
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class PaypackPayTool(Tool):

    def _invoke(
        self,
        tool_parameters: Dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            recipient = tool_parameters.get("recipient", "")
            amount = float(tool_parameters.get("amount") or 0)
            currency = (tool_parameters.get("currency") or "USDC").upper()
            subject = tool_parameters.get("subject", "AI Agent Payment")

            if amount <= 0:
                yield self.create_text_message("Amount must be greater than 0")
                return

            credentials = self.runtime.credentials or {}
            payment_mode = credentials.get("payment_mode", "crypto")

            if currency == "CNY" or payment_mode == "alipay":
                yield from self._pay_alipay(recipient, amount, subject, credentials)
            else:
                yield from self._pay_crypto(recipient, amount, currency, credentials)
        except Exception as e:
            yield self.create_text_message(f"Payment failed: {str(e)}")

    def _pay_crypto(
        self, to: str, amount: float, currency: str, creds: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        from paypack import AgentPay

        private_key = creds.get("private_key") or os.getenv("PRIVATE_KEY")
        if not private_key:
            yield self.create_text_message("Missing private_key in credentials")
            return

        network = creds.get("network", "base-sepolia")
        limit_val = creds.get("spend_limit_daily")
        limit = float(limit_val) if limit_val not in (None, "") else 10.0
        broadcast = str(creds.get("broadcast", "false")).lower() == "true"

        pay = AgentPay(
            wallet_config={"private_key": private_key},
            network=network,
            spend_limit_daily=limit,
            broadcast=broadcast,
        )

        receipt = pay.send(to=to, amount=amount, currency=currency)
        yield self.create_text_message(json.dumps({
            "status": "success",
            "currency": currency,
            "amount": amount,
            "recipient": to,
            "tx_hash": receipt.get("tx_hash"),
            "explorer_link": receipt.get("explorer_link"),
            "daily_remaining": receipt.get("daily_remaining"),
            "timestamp": receipt.get("timestamp"),
        }, ensure_ascii=False, indent=2))

    def _pay_alipay(
        self, buyer_id: str, amount: float, subject: str, creds: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        from paypack.signer.alipay import AlipaySigner
        from paypack import AgentPay

        app_id = creds.get("app_id")
        private_key = creds.get("private_key")
        alipay_public_key = creds.get("alipay_public_key")
        sandbox = str(creds.get("sandbox", "true")).lower() == "true"

        if private_key and ("BEGIN" in private_key or "PRIVATE KEY" in private_key):
            signer = AlipaySigner(
                app_id=app_id, private_key=private_key,
                alipay_public_key=alipay_public_key, sandbox=sandbox,
            )
        else:
            signer = AlipaySigner(
                app_id=app_id, private_key_path=private_key,
                alipay_public_key=alipay_public_key, sandbox=sandbox,
            )

        pay = AgentPay(signer=signer, network="alipay")
        receipt = pay.send(
            to=buyer_id, amount=amount, currency="CNY", subject=subject,
        )

        alipay_resp = receipt.get("alipay_response", receipt)
        yield self.create_text_message(json.dumps({
            "status": "success",
            "currency": "CNY",
            "amount": amount,
            "subject": subject,
            "trade_no": receipt.get("trade_no"),
            "alipay_status": alipay_resp.get("code"),
            "alipay_message": alipay_resp.get("msg", alipay_resp.get("sub_msg", "")),
        }, ensure_ascii=False, indent=2))
