import json
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class CreateOptionsetTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Required parameters
        name: Optional[str] = tool_parameters.get("name")
        options_param: Optional[str] = tool_parameters.get("options")
        enable_color_param: Optional[str] = tool_parameters.get("enable_color")
        enable_score_param: Optional[str] = tool_parameters.get("enable_score")

        if not name or not str(name).strip():
            yield self.create_json_message({"error": "Missing parameter: name"})
            return

        if not options_param or not str(options_param).strip():
            yield self.create_json_message({"error": "Missing parameter: options"})
            return

        if not enable_color_param or not str(enable_color_param).strip():
            yield self.create_json_message({"error": "Missing parameter: enable_color"})
            return

        if not enable_score_param or not str(enable_score_param).strip():
            yield self.create_json_message({"error": "Missing parameter: enable_score"})
            return

        # Parse options data
        try:
            options_data = json.loads(str(options_param))
            if not isinstance(options_data, list):
                yield self.create_json_message({"error": "options parameter must be a JSON array"})
                return
        except json.JSONDecodeError:
            yield self.create_json_message({"error": "Invalid JSON format for options parameter"})
            return

        # Parse boolean parameters
        enable_color = str(enable_color_param).lower() in ("true", "1", "yes")
        enable_score = str(enable_score_param).lower() in ("true", "1", "yes")

        # Build request body
        body = {
            "name": str(name).strip(),
            "options": options_data,
            "enableColor": enable_color,
            "enableScore": enable_score
        }

        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.post("/v3/app/optionsets", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return