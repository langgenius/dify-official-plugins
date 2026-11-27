from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import DealportApiError, parse_bool, request_dealport, split_csv_list


class PreviewCompaniesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        state = str(tool_parameters.get("state") or "").strip().upper()
        if state and len(state) != 2:
            yield self.create_text_message("Error: state must be a two-letter US state code (for example OH, TX, FL).")
            return

        body: dict[str, Any] = {
            "q": (tool_parameters.get("q") or "").strip() or None,
            "state": state or None,
            "cities": split_csv_list(tool_parameters.get("cities")) or None,
            "counties": split_csv_list(tool_parameters.get("counties")) or None,
            "naics": split_csv_list(tool_parameters.get("naics")) or None,
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
        }

        try:
            result = request_dealport(self.runtime.credentials, "POST", "/companies/preview", json_body=body)
        except DealportApiError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return

        total = result.get("total") or result.get("total_count") or result.get("count") or 0
        samples = result.get("sample_companies") or result.get("companies") or result.get("items") or []
        lines = [f"Dealport market preview matched {total} US companies ($0.00)."]
        for item in samples[:5]:
            if isinstance(item, dict):
                name = item.get("name") or item.get("legal_name") or "Unknown"
                loc = ", ".join(filter(None, [item.get("city"), item.get("state")]))
                cid = item.get("id") or item.get("company_id") or ""
                suffix = f" ({loc})" if loc else ""
                id_part = f" [id: {cid}]" if cid else ""
                lines.append(f"- {name}{suffix}{id_part}")

        yield self.create_json_message(result)
        yield self.create_text_message("\n".join(lines))
