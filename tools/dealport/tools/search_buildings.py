from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import DealportApiError, request_dealport

VALID_BOROUGHS = {"MN", "BK", "QN", "BX", "SI"}
VALID_LOAN_HOLDERS = {"agency", "cmbs", "bank"}
VALID_SIGNALS = {
    "rent_stabilized",
    "dob_penalties",
    "housing_court",
    "tax_lien",
    "ll97",
    "section8_expiring",
    "tax_credit_ending",
    "failing_inspection",
}


class SearchBuildingsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        borough = str(tool_parameters.get("borough") or "").strip().upper()
        if borough not in VALID_BOROUGHS:
            yield self.create_text_message("Error: borough must be one of MN, BK, QN, BX, or SI.")
            return

        loan_holder = str(tool_parameters.get("loan_holder") or "").strip().lower()
        if loan_holder and loan_holder not in VALID_LOAN_HOLDERS:
            yield self.create_text_message("Error: loan_holder must be one of agency, cmbs, or bank.")
            return

        signal = str(tool_parameters.get("signal") or "").strip().lower()
        if signal and signal not in VALID_SIGNALS:
            yield self.create_text_message(
                f"Error: signal must be one of {', '.join(sorted(VALID_SIGNALS))}."
            )
            return

        limit_raw = tool_parameters.get("limit", 25)
        limit = int(limit_raw) if limit_raw is not None else 25
        if limit < 1 or limit > 50:
            yield self.create_text_message("Error: limit must be between 1 and 50.")
            return

        params: dict[str, Any] = {
            "borough": borough,
            "min_units": int(tool_parameters["min_units"])
            if tool_parameters.get("min_units") is not None
            else None,
            "q": (tool_parameters.get("q") or "").strip() or None,
            "loan_due_by": int(tool_parameters["loan_due_by"])
            if tool_parameters.get("loan_due_by") is not None
            else None,
            "loan_holder": loan_holder or None,
            "signal": signal or None,
            "limit": limit,
            "cursor": (tool_parameters.get("cursor") or "").strip() or None,
        }

        try:
            result = request_dealport(self.runtime.credentials, "GET", "/buildings", params=params)
        except DealportApiError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return

        buildings = result.get("buildings") or result.get("items") or result.get("results") or []
        lines = [f"Returned {len(buildings)} Dealport building Record(s) in {borough}."]
        for bldg in buildings[:10]:
            if isinstance(bldg, dict):
                addr = bldg.get("address") or bldg.get("street_address") or "Unknown address"
                bbl = bldg.get("bbl") or bldg.get("id") or ""
                units = bldg.get("units") or bldg.get("residential_units")
                unit_part = f" ({units} units)" if units is not None else ""
                bbl_part = f" [BBL: {bbl}]" if bbl else ""
                lines.append(f"- {addr}{unit_part}{bbl_part}")

        yield self.create_json_message(result)
        yield self.create_text_message("\n".join(lines))
