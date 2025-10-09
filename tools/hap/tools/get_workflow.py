from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class GetWorkflowTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        process_id: Optional[str] = tool_parameters.get("process_id")
        if not process_id or not str(process_id).strip():
            yield self.create_json_message({"error": "Missing parameter: process_id"})
            return

        process_id = str(process_id).strip()

        try:
            client = HapRequest(self.runtime.credentials)
            # Note: Workflow API uses a different base path "/workflow"
            resp: Dict[str, Any] = client.get(f"/v3/app/workflow/processes/{process_id}")
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return