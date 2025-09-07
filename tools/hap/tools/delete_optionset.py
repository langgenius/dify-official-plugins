from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class DeleteOptionsetTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        optionset_id: Optional[str] = tool_parameters.get("optionset_id")
        if not optionset_id or not str(optionset_id).strip():
            yield self.create_json_message({"error": "Missing parameter: optionset_id"})
            return

        optionset_id = str(optionset_id).strip()

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.delete(f"/v3/app/optionsets/{optionset_id}")
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return