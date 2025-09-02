import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class GetRecordShareLinkTool(Tool):
    def _parse_field_ids(self, fields_param: Optional[str]) -> List[str]:
        """Parse comma-separated string or JSON array into list of strings"""
        if not fields_param:
            return []
        
        fields_param = str(fields_param).strip()
        if not fields_param:
            return []
            
        # Try to parse as JSON array first
        try:
            parsed = json.loads(fields_param)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        
        # Parse as comma-separated string
        return [field_str.strip() for field_str in fields_param.split(",") if field_str.strip()]

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

        # Build request body
        body = {}

        # Parse visible fields
        visible_fields = self._parse_field_ids(tool_parameters.get("visible_fields"))
        if visible_fields:
            body["visibleFields"] = visible_fields

        # Optional parameters
        expired_in = tool_parameters.get("expired_in")
        if expired_in is not None:
            body["expiredIn"] = int(expired_in)

        password = tool_parameters.get("password")
        if password is not None:
            body["password"] = str(password)

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.post(f"/v3/app/worksheets/{worksheet_id}/rows/{row_id}/share-link", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return