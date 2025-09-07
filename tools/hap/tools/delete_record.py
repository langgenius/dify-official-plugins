from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class DeleteRecordTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Params
        worksheet_id: Optional[str] = tool_parameters.get("worksheet_id")
        if not worksheet_id or not str(worksheet_id).strip():
            yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
            return
        worksheet_id = str(worksheet_id).strip()

        row_id: Optional[str] = tool_parameters.get("row_id")
        if not row_id or not str(row_id).strip():
            yield self.create_json_message({"error": "Missing parameter: row_id"})
            return
        row_id = str(row_id).strip()

        do_not_trigger = tool_parameters.get("do_not_trigger_workflow")
        permanent = tool_parameters.get("permanent")

        payload: Dict[str, Any] = {}
        # Default: triggerWorkflow true unless do_not_trigger_workflow == true
        payload["triggerWorkflow"] = True if do_not_trigger is None else (not bool(do_not_trigger))
        if isinstance(permanent, bool):
            payload["permanent"] = permanent

        # Request
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.delete(
                f"/v3/app/worksheets/{worksheet_id}/rows/{row_id}",
                json_body=payload,
            )
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return
