import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class UpdateRecordTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

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

        # Parse body
        body_param = tool_parameters.get("body")
        body_obj: Optional[Dict[str, Any]] = None
        if isinstance(body_param, str):
            try:
                body_obj = json.loads(body_param)
            except Exception as e:
                yield self.create_json_message({"error": f"Invalid JSON for body: {e}"})
                return
        elif isinstance(body_param, dict):
            body_obj = body_param
        else:
            yield self.create_json_message({"error": "Missing or invalid parameter: body"})
            return

        if not isinstance(body_obj, dict) or not body_obj:
            yield self.create_json_message({"error": "Body must be a non-empty JSON object of {fieldId/alias: value}"})
            return

        # do_not_trigger_workflow flag (inverse for API's triggerWorkflow)
        do_not_trigger = tool_parameters.get("do_not_trigger_workflow")
        trigger_workflow_bool = True if do_not_trigger is None else (not bool(do_not_trigger))

        # Map to OpenAPI "fields" array
        fields: List[Dict[str, Any]] = []
        try:
            for k, v in body_obj.items():
                fields.append({"id": str(k), "value": v})
        except Exception as e:
            yield self.create_json_message({"error": f"Failed to build fields payload: {e}"})
            return

        payload: Dict[str, Any] = {
            "fields": fields,
            "triggerWorkflow": trigger_workflow_bool,
        }

        # Request
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.patch(f"/v3/app/worksheets/{worksheet_id}/rows/{row_id}", json_body=payload)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return
