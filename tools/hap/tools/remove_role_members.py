import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class RemoveRoleMembersTool(Tool):
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

        role_id: Optional[str] = tool_parameters.get("role_id")
        if not role_id or not str(role_id).strip():
            yield self.create_json_message({"error": "Missing parameter: role_id"})
            return

        operator_id: Optional[str] = tool_parameters.get("operator_id")
        if not operator_id or not str(operator_id).strip():
            yield self.create_json_message({"error": "Missing parameter: operator_id"})
            return

        role_id = str(role_id).strip()
        operator_id = str(operator_id).strip()

        # Parse member parameters (all required by API spec)
        account_ids = self._parse_ids(tool_parameters.get("account_ids"))
        department_ids = self._parse_ids(tool_parameters.get("department_ids"))
        department_tree_ids = self._parse_ids(tool_parameters.get("department_tree_ids"))
        job_ids = self._parse_ids(tool_parameters.get("job_ids"))
        org_role_ids = self._parse_ids(tool_parameters.get("org_role_ids"))

        # Build request body (all fields are required by API spec)
        body = {
            "operatorId": operator_id,
            "accountIds": account_ids,
            "departmentIds": department_ids,
            "departmentTreeIds": department_tree_ids,
            "jobIds": job_ids,
            "orgRoleIds": org_role_ids
        }

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.delete(f"/v3/app/roles/{role_id}/members", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return