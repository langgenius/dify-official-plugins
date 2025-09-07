from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class PublicFindDepartmentTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Optional query
        name: Optional[str] = tool_parameters.get("name")
        params: Dict[str, Any] = {}
        if isinstance(name, str) and name.strip():
            params["name"] = name.strip()

        # Request
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.get("/v3/departments/lookup", params=params)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return
