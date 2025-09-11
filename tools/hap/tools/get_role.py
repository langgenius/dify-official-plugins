from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class GetRoleTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        role_id: Optional[str] = tool_parameters.get("role_id")
        if not role_id or not str(role_id).strip():
            yield self.create_json_message({"error": "Missing parameter: role_id"})
            return

        role_id = str(role_id).strip()

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.get(f"/v3/app/roles/{role_id}")
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return