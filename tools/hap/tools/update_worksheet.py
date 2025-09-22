import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class UpdateWorksheetTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        # Required: worksheet_id
        worksheet_id_param = tool_parameters.get("worksheet_id")
        if not worksheet_id_param or not str(worksheet_id_param).strip():
            yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
            return
        worksheet_id: str = str(worksheet_id_param).strip()

        # Optional primitive fields
        name_param = tool_parameters.get("name")
        alias_param = tool_parameters.get("alias")
        section_id_param = tool_parameters.get("section_id")

        # Optional complex fields: add_fields / edit_fields / remove_fields (JSON arrays)
        add_fields_param = tool_parameters.get("add_fields")
        edit_fields_param = tool_parameters.get("edit_fields")
        remove_fields_param = tool_parameters.get("remove_fields")

        add_fields_list: Optional[List[Any]] = None
        edit_fields_list: Optional[List[Any]] = None
        remove_fields_list: Optional[List[Any]] = None

        # Helpers
        def _parse_json_array(param_value: Any, field_name: str) -> Optional[List[Any]]:
            if param_value is None:
                return None
            if isinstance(param_value, str):
                try:
                    parsed = json.loads(param_value)
                except Exception as e:
                    raise ValueError(f"Invalid JSON for {field_name}: {e}")
            else:
                parsed = param_value
            if not isinstance(parsed, list):
                raise ValueError(f"Invalid parameter: {field_name} must be a JSON array")
            return parsed

        try:
            add_fields_list = _parse_json_array(add_fields_param, "add_fields")
            edit_fields_list = _parse_json_array(edit_fields_param, "edit_fields")
            remove_fields_list = _parse_json_array(remove_fields_param, "remove_fields")
        except ValueError as ve:
            yield self.create_json_message({"error": str(ve)})
            return

        # Build payload per OpenAPI (POST /v3/app/worksheets/{worksheet_id})
        payload: Dict[str, Any] = {}

        if isinstance(name_param, str) and name_param.strip():
            payload["name"] = name_param.strip()
        if isinstance(alias_param, str) and alias_param.strip():
            payload["alias"] = alias_param.strip()
        if isinstance(section_id_param, str) and section_id_param.strip():
            payload["sectionId"] = section_id_param.strip()

        if add_fields_list is not None:
            payload["addFields"] = add_fields_list
        if edit_fields_list is not None:
            payload["editFields"] = edit_fields_list
        if remove_fields_list is not None:
            payload["removeFields"] = remove_fields_list

        if not payload:
            yield self.create_json_message({"error": "No changes provided: specify at least one of name, alias, section_id, add_fields, edit_fields, remove_fields"})
            return

        # Request (OpenAPI shows POST for update)
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.post(f"/v3/app/worksheets/{worksheet_id}", json_body=payload)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return
