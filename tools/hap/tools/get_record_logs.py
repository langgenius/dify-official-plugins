from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class GetRecordLogsTool(Tool):
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
        
        operator_ids = tool_parameters.get("operator_ids")
        if operator_ids:
            # Parse comma-separated operator IDs
            operator_ids_list = [id_str.strip() for id_str in str(operator_ids).split(",") if id_str.strip()]
            if operator_ids_list:
                params["opeartorIds"] = operator_ids_list  # Note: API has typo "opeartorIds"

        field = tool_parameters.get("field")
        if field:
            params["field"] = str(field).strip()

        page_index = tool_parameters.get("page_index")
        if page_index is not None:
            params["pageIndex"] = str(page_index)

        page_size = tool_parameters.get("page_size")
        if page_size is not None:
            params["pageSize"] = str(page_size)

        start_date = tool_parameters.get("start_date")
        if start_date:
            params["startDate"] = str(start_date).strip()

        end_date = tool_parameters.get("end_date")
        if end_date:
            params["endDate"] = str(end_date).strip()

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.get(f"/v3/app/worksheets/{worksheet_id}/rows/{row_id}/logs", params=params)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return