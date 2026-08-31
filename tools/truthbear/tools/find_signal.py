# DO NOT EDIT — generated from truth/ by scripts/gen.mjs
# truth-sha: 540d5ca39fd40903
# Edit truth/service.json or truth/tools.json instead, then run: node scripts/gen.mjs

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from _config import DISCLOSURE, PRICING_URL
from tools._http import call


class FindSignalTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        industry = tool_parameters.get("industry")
        signal_id = tool_parameters.get("signal_id")
        entity = tool_parameters.get("entity")
        full = tool_parameters.get("full")
        narrowed = bool(industry or signal_id)
        params = {"industry": industry, "signal_id": signal_id, "entity": entity}
        if not (full and narrowed):
            # Un-narrowed detail is about 5.4 MB and does not fit in a model context.
            params["summary"] = "1"
        status, body = call(
            "/gauge/coverage",
            params,
        )

        if status >= 400:
            # The service explains refusals in the body (including when it did not charge you).
            # Passing that through beats replacing it with a generic error.
            yield self.create_json_message({"status": status, **body})
            return

        if full and not narrowed:
            body = dict(body)
            body["_truthbear_note"] = (
                "Returned the compact summary, not the full detail you asked for: un-narrowed "
                "detail is about 5.4 MB and would not fit in a model context. Pass industry or "
                "signal_id together with full to get it."
            )

        yield self.create_json_message(body)
