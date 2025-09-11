from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class DeleteWorksheetTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Params
        worksheet_id_param: Optional[str] = tool_parameters.get("worksheet_id")
        if not worksheet_id_param or not str(worksheet_id_param).strip():
            yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
            return
        worksheet_id: str = str(worksheet_id_param).strip()

        # Request
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.delete(f"/v3/app/worksheets/{worksheet_id}")
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return
