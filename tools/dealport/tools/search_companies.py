from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import DealportApiError, parse_bool, request_dealport


class SearchCompaniesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        state = str(tool_parameters.get("state") or "").strip().upper()
        if state and len(state) != 2:
            yield self.create_text_message("Error: state must be a two-letter US state code (for example OH, TX, FL).")
            return

        limit_raw = tool_parameters.get("limit", 25)
        limit = int(limit_raw) if limit_raw is not None else 25
        if limit < 1 or limit > 50:
            yield self.create_text_message("Error: limit must be between 1 and 50.")
            return

        params: dict[str, Any] = {
            "q": (tool_parameters.get("q") or "").strip() or None,
            "state": state or None,
            "cities": (tool_parameters.get("cities") or "").strip() or None,
            "counties": (tool_parameters.get("counties") or "").strip() or None,
            "naics": (tool_parameters.get("naics") or "").strip() or None,
            "domain": (tool_parameters.get("domain") or "").strip() or None,
            "min_employees": int(tool_parameters["min_employees"])
            if tool_parameters.get("min_employees") is not None
            else None,
            "max_employees": int(tool_parameters["max_employees"])
            if tool_parameters.get("max_employees") is not None
            else None,
            "min_revenue": float(tool_parameters["min_revenue"])
            if tool_parameters.get("min_revenue") is not None
            else None,
            "max_revenue": float(tool_parameters["max_revenue"])
            if tool_parameters.get("max_revenue") is not None
            else None,
            "independent": parse_bool(tool_parameters.get("independent")),
            "limit": limit,
            "cursor": (tool_parameters.get("cursor") or "").strip() or None,
        }

        try:
            result = request_dealport(self.runtime.credentials, "GET", "/companies", params=params)
        except DealportApiError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return

        records = result.get("companies") or result.get("items") or result.get("results") or []
        lines = [f"Returned {len(records)} Dealport company Record(s)."]
        for item in records[:10]:
            if isinstance(item, dict):
                name = item.get("name") or item.get("legal_name") or "Unknown"
                loc = ", ".join(filter(None, [item.get("city"), item.get("state")]))
                cid = item.get("id") or item.get("company_id") or ""
                suffix = f" ({loc})" if loc else ""
                id_part = f" [id: {cid}]" if cid else ""
                lines.append(f"- {name}{suffix}{id_part}")

        yield self.create_json_message(result)
        yield self.create_text_message("\n".join(lines))
