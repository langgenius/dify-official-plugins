from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class UserLeaveAllRolesTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        user_id: Optional[str] = tool_parameters.get("user_id")
        if not user_id or not str(user_id).strip():
            yield self.create_json_message({"error": "Missing parameter: user_id"})
            return

        user_id = str(user_id).strip()

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.delete(f"/v3/app/roles/users/{user_id}")
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return