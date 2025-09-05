import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional, Union

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class AddRoleMembersTool(Tool):
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

        role_id: Optional[str] = tool_parameters.get("role_id")
        if not role_id or not str(role_id).strip():
            yield self.create_json_message({"error": "Missing parameter: role_id"})
            return

        role_id = str(role_id).strip()

        # Parse member parameters
        user_ids = self._parse_ids(tool_parameters.get("user_ids"))
        department_ids = self._parse_ids(tool_parameters.get("department_ids"))
        department_tree_ids = self._parse_ids(tool_parameters.get("department_tree_ids"))
        job_ids = self._parse_ids(tool_parameters.get("job_ids"))
        org_role_ids = self._parse_ids(tool_parameters.get("org_role_ids"))

        # Build request body
        body = {}
        if user_ids:
            body["userIds"] = user_ids
        if department_ids:
            body["departmentIds"] = department_ids
        if department_tree_ids:
            body["departmentTreeIds"] = department_tree_ids
        if job_ids:
            body["jobIds"] = job_ids
        if org_role_ids:
            body["orgRoleIds"] = org_role_ids

        if not body:
            yield self.create_json_message({"error": "At least one member type must be specified"})
            return

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.post(f"/v3/app/roles/{role_id}/members", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return