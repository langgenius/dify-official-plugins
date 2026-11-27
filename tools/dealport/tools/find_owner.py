import re
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import DealportApiError, request_dealport

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class FindOwnerTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        company_id = str(tool_parameters.get("company_id") or "").strip()
        if not UUID_RE.match(company_id):
            yield self.create_text_message("Error: company_id must be a valid Dealport company UUID.")
            return

        person = str(tool_parameters.get("person") or "").strip()
        body: dict[str, Any] = {"company_id": company_id}
        if person:
            body["person"] = person

        try:
            result = request_dealport(self.runtime.credentials, "POST", "/owners", json_body=body)
        except DealportApiError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return

        owner_obj = result.get("owner")
        owner_name = (
            result.get("owner_name")
            or (owner_obj.get("name") if isinstance(owner_obj, dict) else None)
            or result.get("name")
        )
        summary = (
            f"Resolved verified owner {owner_name} for company {company_id}."
            if owner_name
            else f"Completed owner lookup for company {company_id}."
        )
        yield self.create_json_message(result)
        yield self.create_text_message(summary)
