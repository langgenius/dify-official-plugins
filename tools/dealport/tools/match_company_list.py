import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import DealportApiError, request_dealport


class MatchCompanyListTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        csv_text = str(tool_parameters.get("csv") or "").strip()
        items_json = str(tool_parameters.get("items_json") or "").strip()

        if not csv_text and not items_json:
            yield self.create_text_message("Error: provide either csv or items_json to match companies.")
            return

        body: dict[str, Any] = {"watch": False}
        if items_json:
            try:
                parsed = json.loads(items_json)
            except json.JSONDecodeError as exc:
                yield self.create_text_message(f"Error: items_json must be valid JSON ({exc.msg}).")
                return
            if not isinstance(parsed, list) or not parsed or len(parsed) > 250:
                yield self.create_text_message("Error: items_json must be a non-empty JSON array of 1 to 250 objects.")
                return
            if not all(isinstance(entry, dict) for entry in parsed):
                yield self.create_text_message("Error: every element in items_json must be a JSON object.")
                return
            body["items"] = parsed
        else:
            body["csv"] = csv_text

        try:
            result = request_dealport(self.runtime.credentials, "POST", "/companies/match", json_body=body)
        except DealportApiError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return

        matches = result.get("matches") or result.get("items") or result.get("results") or []
        yield self.create_json_message(result)
        yield self.create_text_message(f"Matched {len(matches)} company row(s) against Dealport ($0.00).")
