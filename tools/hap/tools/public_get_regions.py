from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class PublicGetRegionsTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Optional query params
        region_id: Optional[str] = tool_parameters.get("id")
        search: Optional[str] = tool_parameters.get("search")
        params: Dict[str, Any] = {}
        if isinstance(region_id, str) and region_id.strip():
            params["id"] = region_id.strip()
        if isinstance(search, str) and search.strip():
            params["search"] = search.strip()

        # Request
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.get("/v3/regions", params=params)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return
