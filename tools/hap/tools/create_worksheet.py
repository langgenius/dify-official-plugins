import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class CreateWorksheetTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Required: name
        name_param = tool_parameters.get("name")
        if not name_param or not str(name_param).strip():
            yield self.create_json_message({"error": "Missing parameter: name"})
            return
        name: str = str(name_param).strip()

        # Required: fields (JSON array)
        fields_param = tool_parameters.get("fields")
        fields_list: Optional[List[Any]] = None
        if isinstance(fields_param, str):
            try:
                parsed = json.loads(fields_param)
            except Exception as e:
                yield self.create_json_message({"error": f"Invalid JSON for fields: {e}"})
                return
            if not isinstance(parsed, list):
                yield self.create_json_message({"error": "Invalid parameter: fields must be a JSON array"})
                return
            fields_list = parsed
        elif isinstance(fields_param, list):
            fields_list = fields_param  # allow direct list
        else:
            yield self.create_json_message({"error": "Missing or invalid parameter: fields"})
            return

        if not fields_list:
            yield self.create_json_message({"error": "Invalid parameter: fields must be a non-empty JSON array"})
            return

        # Optional params
        alias_param = tool_parameters.get("alias")
        section_id_param = tool_parameters.get("section_id")

        # Build payload per OpenAPI
        payload: Dict[str, Any] = {
            "name": name,
            "fields": fields_list,
        }
        if isinstance(alias_param, str) and alias_param.strip():
            payload["alias"] = alias_param.strip()
        if isinstance(section_id_param, str) and section_id_param.strip():
            payload["sectionId"] = section_id_param.strip()

        # Request
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.post("/v3/app/worksheets", json_body=payload)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return
