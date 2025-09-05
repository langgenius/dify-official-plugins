import json
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class TriggerWorkflowTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        process_id: Optional[str] = tool_parameters.get("process_id")
        if not process_id or not str(process_id).strip():
            yield self.create_json_message({"error": "Missing parameter: process_id"})
            return

        inputs_param: Optional[str] = tool_parameters.get("inputs")
        if not inputs_param or not str(inputs_param).strip():
            yield self.create_json_message({"error": "Missing parameter: inputs"})
            return

        process_id = str(process_id).strip()

        # Parse inputs parameter
        try:
            inputs_data = json.loads(str(inputs_param))
            if not isinstance(inputs_data, dict):
                yield self.create_json_message({"error": "inputs parameter must be a JSON object"})
                return
        except json.JSONDecodeError:
            yield self.create_json_message({"error": "Invalid JSON format for inputs parameter"})
            return

        try:
            client = HapRequest(self.runtime.credentials)
            # Note: Workflow API uses a different base path "/workflow"
            resp: Dict[str, Any] = client.post(f"/v3/app/workflow/hooks/{process_id}", json_body=inputs_data)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return