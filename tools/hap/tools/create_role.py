import json
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class CreateRoleTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Required parameters
        name: Optional[str] = tool_parameters.get("name")
        description: Optional[str] = tool_parameters.get("description")
        permission_scope: Optional[str] = tool_parameters.get("permission_scope")

        if not name or not str(name).strip():
            yield self.create_json_message({"error": "Missing parameter: name"})
            return

        if not description or not str(description).strip():
            yield self.create_json_message({"error": "Missing parameter: description"})
            return

        if not permission_scope or not str(permission_scope).strip():
            yield self.create_json_message({"error": "Missing parameter: permission_scope"})
            return

        # Build request body
        body = {
            "name": str(name).strip(),
            "description": str(description).strip(),
            "permissionScope": str(permission_scope).strip(),
            "type": tool_parameters.get("role_type", "0")
        }

        # Optional parameters
        hide_app = tool_parameters.get("hide_app_for_members")
        if hide_app is not None:
            body["hideAppForMembers"] = str(hide_app).lower()

        # Parse JSON parameters
        global_permissions = tool_parameters.get("global_permissions")
        if global_permissions:
            try:
                body["globalPermissions"] = json.loads(str(global_permissions))
            except json.JSONDecodeError:
                yield self.create_json_message({"error": "Invalid JSON format for global_permissions"})
                return

        worksheet_permissions = tool_parameters.get("worksheet_permissions")
        if worksheet_permissions:
            try:
                body["worksheetPermissions"] = json.loads(str(worksheet_permissions))
            except json.JSONDecodeError:
                yield self.create_json_message({"error": "Invalid JSON format for worksheet_permissions"})
                return

        page_permissions = tool_parameters.get("page_permissions")
        if page_permissions:
            try:
                body["pagePermissions"] = json.loads(str(page_permissions))
            except json.JSONDecodeError:
                yield self.create_json_message({"error": "Invalid JSON format for page_permissions"})
                return

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.post("/v3/app/roles", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return