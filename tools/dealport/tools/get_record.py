import re
from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import DealportApiError, request_dealport

SAFE_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


class GetRecordTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        record_id = str(tool_parameters.get("record_id") or "").strip()
        if not SAFE_RECORD_ID_RE.match(record_id):
            yield self.create_text_message(
                "Error: record_id must be a valid Dealport company UUID or 10-digit NYC BBL."
            )
            return

        try:
            result = request_dealport(
                self.runtime.credentials,
                "GET",
                f"/records/{quote(record_id, safe='')}",
            )
        except DealportApiError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return

        record = result.get("record") if isinstance(result.get("record"), dict) else result
        title = (
            record.get("name")
            or record.get("legal_name")
            or record.get("address")
            or record_id
        )
        yield self.create_json_message(result)
        yield self.create_text_message(f"Retrieved Dealport Record: {title} ({record_id}).")
