import json
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class BatchCreateRecordsTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        worksheet_id: Optional[str] = tool_parameters.get("worksheet_id")
        if not worksheet_id or not str(worksheet_id).strip():
            yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
            return

        rows_param: Optional[str] = tool_parameters.get("rows")
        if not rows_param or not str(rows_param).strip():
            yield self.create_json_message({"error": "Missing parameter: rows"})
            return

        worksheet_id = str(worksheet_id).strip()

        # Parse rows data
        try:
            rows_data = json.loads(str(rows_param))
            if not isinstance(rows_data, list):
                yield self.create_json_message({"error": "rows parameter must be a JSON array"})
                return
        except json.JSONDecodeError:
            yield self.create_json_message({"error": "Invalid JSON format for rows parameter"})
            return

        # Build request body
        body = {"rows": rows_data}

        # Optional trigger workflow parameter
        do_not_trigger_workflow = tool_parameters.get("do_not_trigger_workflow")
        if do_not_trigger_workflow is not None:
            do_not_trigger_workflow_bool = str(do_not_trigger_workflow).lower() in ("true", "1", "yes")
            body["triggerWorkflow"] = not do_not_trigger_workflow_bool

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.post(f"/v3/app/worksheets/{worksheet_id}/rows/batch", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return