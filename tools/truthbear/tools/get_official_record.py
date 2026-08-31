# DO NOT EDIT — generated from truth/ by scripts/gen.mjs
# truth-sha: 540d5ca39fd40903
# Edit truth/service.json or truth/tools.json instead, then run: node scripts/gen.mjs

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from _config import DISCLOSURE, PRICING_URL
from tools._http import call


class GetOfficialRecordTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        status, body = call(
            "/gauge",
            {"signal_id": tool_parameters.get("signal_id"), "entity": tool_parameters.get("entity"), "dim": tool_parameters.get("dim")},
        )

        if status == 402:
            # ★ This plugin does not pay. Dify's Marketplace Agreement 4.2(b) forbids building a
            #   purchase function into a plugin; 4.2(c) allows relying on an external paid service
            #   as long as it is clearly disclosed. So we hand the live challenge back as data and
            #   let the person decide, with the server's own guidance attached.
            yield self.create_json_message(
                {
                    "paid": False,
                    "accepts": body.get("accepts"),
                    "client_hint": body.get("client_hint"),
                    "pricing_url": PRICING_URL,
                    "disclosure": DISCLOSURE,
                }
            )
            return

        if status >= 400:
            # The service explains refusals in the body (including when it did not charge you).
            # Passing that through beats replacing it with a generic error.
            yield self.create_json_message({"status": status, **body})
            return

        yield self.create_json_message(body)
