import json
from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class GetRecordPivotTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Parameter validation

        worksheet_id: Optional[str] = tool_parameters.get("worksheet_id")
        if not worksheet_id or not str(worksheet_id).strip():
            yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
            return

        values_param: Optional[str] = tool_parameters.get("values")
        if not values_param or not str(values_param).strip():
            yield self.create_json_message({"error": "Missing parameter: values"})
            return

        worksheet_id = str(worksheet_id).strip()

        # Parse required values parameter
        try:
            values_data = json.loads(str(values_param))
            if not isinstance(values_data, list):
                yield self.create_json_message({"error": "values parameter must be a JSON array"})
                return
        except json.JSONDecodeError:
            yield self.create_json_message({"error": "Invalid JSON format for values parameter"})
            return

        # Build request body
        body = {"values": values_data}

        # Parse optional JSON parameters
        for param_name in ["columns", "rows", "filter", "sorts"]:
            param_value = tool_parameters.get(param_name)
            if param_value:
                try:
                    parsed_data = json.loads(str(param_value))
                    body[param_name] = parsed_data
                except json.JSONDecodeError:
                    yield self.create_json_message({"error": f"Invalid JSON format for {param_name} parameter"})
                    return

        # Optional string/number parameters
        view_id = tool_parameters.get("view_id")
        if view_id:
            body["viewId"] = str(view_id).strip()

        page_index = tool_parameters.get("page_index")
        if page_index is not None:
            body["pageIndex"] = int(page_index)

        page_size = tool_parameters.get("page_size")
        if page_size is not None:
            page_size_int = int(page_size)
            if page_size_int > 1000:
                yield self.create_json_message({"error": "page_size cannot exceed 1000"})
                return
            body["pageSize"] = page_size_int

        include_summary = tool_parameters.get("include_summary")
        if include_summary is not None:
            include_summary_bool = str(include_summary).lower() in ("true", "1", "yes")
            body["includeSummary"] = include_summary_bool

        try:
            client = HapRequest(self.runtime.credentials)
            # Note: This API uses a different base path "/report" instead of the standard path
            resp: Dict[str, Any] = client.post(f"/v3/app/worksheets/{worksheet_id}/rows/pivot", json_body=body)
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        yield self.create_json_message(resp)
        return