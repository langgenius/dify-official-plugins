import json
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class PaypackRefundTool(Tool):

    def _invoke(
        self,
        tool_parameters: Dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        trade_no = tool_parameters.get("trade_no", "")
        refund_amount = tool_parameters.get("refund_amount")

        if not trade_no:
            yield self.create_text_message("Missing trade number / order ID")
            return

        credentials = self.runtime.credentials or {}

        try:
            from paypack.signer.alipay import AlipaySigner

            app_id = credentials.get("app_id")
            private_key = credentials.get("private_key")
            alipay_public_key = credentials.get("alipay_public_key")
            sandbox = credentials.get("sandbox", "true").lower() == "true"

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

            amount = float(refund_amount) if refund_amount else 0.0
            result = signer.refund(trade_no, amount)
            resp = result.get("alipay_trade_refund_response", result)

            yield self.create_text_message(json.dumps({
                "trade_no": trade_no,
                "refund_amount": amount,
                "code": resp.get("code"),
                "message": resp.get("msg", resp.get("sub_msg", "")),
                "refund_status": "success" if resp.get("code") == "10000" else "failed",
            }, ensure_ascii=False, indent=2))

        except Exception as e:
            yield self.create_text_message(f"Refund failed: {str(e)}")
