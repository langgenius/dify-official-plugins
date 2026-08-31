# DO NOT EDIT — generated from truth/ by scripts/gen.mjs
# truth-sha: 540d5ca39fd40903
# Edit truth/service.json or truth/tools.json instead, then run: node scripts/gen.mjs

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from _config import DISCLOSURE, PRICING_URL
from tools._http import call


class PurchaseOptionsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        status, body = call(
            "/buy",
            {"path": tool_parameters.get("path")},
        )

        if status >= 400:
            # The service explains refusals in the body (including when it did not charge you).
            # Passing that through beats replacing it with a generic error.
            yield self.create_json_message({"status": status, **body})
            return

        yield self.create_json_message(body)
