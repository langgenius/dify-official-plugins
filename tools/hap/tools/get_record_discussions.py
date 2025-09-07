from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class GetRecordDiscussionsTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        worksheet_id: Optional[str] = tool_parameters.get("worksheet_id")
        if not worksheet_id or not str(worksheet_id).strip():
            yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
            return

        row_id: Optional[str] = tool_parameters.get("row_id")
        if not row_id or not str(row_id).strip():
            yield self.create_json_message({"error": "Missing parameter: row_id"})
            return

        worksheet_id = str(worksheet_id).strip()
        row_id = str(row_id).strip()

        # Build query parameters
        params = {}
        
        page_index = tool_parameters.get("page_index")
        if page_index is not None:
            params["pageIndex"] = int(page_index)

        page_size = tool_parameters.get("page_size")
        if page_size is not None:
            params["pageSize"] = int(page_size)

        search = tool_parameters.get("search")
        if search:
            params["search"] = str(search).strip()

        only_with_attachments = tool_parameters.get("only_with_attachments")
        if only_with_attachments is not None:
            only_with_attachments_bool = str(only_with_attachments).lower() in ("true", "1", "yes")
            params["onlyWithAttachments"] = only_with_attachments_bool

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.get(f"/v3/app/worksheets/{worksheet_id}/rows/{row_id}/discussions", params=params)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return