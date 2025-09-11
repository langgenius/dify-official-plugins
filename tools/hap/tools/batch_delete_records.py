import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class BatchDeleteRecordsTool(Tool):
    def _parse_ids(self, ids_param: Optional[str]) -> List[str]:
        """Parse comma-separated string or JSON array into list of strings"""
        if not ids_param:
            return []
        
        ids_param = str(ids_param).strip()
        if not ids_param:
            return []
            
        # Try to parse as JSON array first
        try:
            parsed = json.loads(ids_param)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        
        # Parse as comma-separated string
        return [id_str.strip() for id_str in ids_param.split(",") if id_str.strip()]

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        worksheet_id: Optional[str] = tool_parameters.get("worksheet_id")
        if not worksheet_id or not str(worksheet_id).strip():
            yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
            return

        worksheet_id = str(worksheet_id).strip()

        # Parse row IDs
        row_ids = self._parse_ids(tool_parameters.get("row_ids"))
        if not row_ids:
            yield self.create_json_message({"error": "Missing parameter: row_ids"})
            return

        # Build request body
        body = {"rowIds": row_ids}

        # Optional parameters
        permanent = tool_parameters.get("permanent")
        if permanent is not None:
            permanent_bool = str(permanent).lower() in ("true", "1", "yes")
            body["permanent"] = permanent_bool

        do_not_trigger_workflow = tool_parameters.get("do_not_trigger_workflow")
        if do_not_trigger_workflow is not None:
            do_not_trigger_workflow_bool = str(do_not_trigger_workflow).lower() in ("true", "1", "yes")
            body["triggerWorkflow"] = not do_not_trigger_workflow_bool

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.delete(f"/v3/app/worksheets/{worksheet_id}/rows/batch", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return