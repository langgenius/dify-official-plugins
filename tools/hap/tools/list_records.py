import json
from collections.abc import Generator
from typing import Any, Dict, List, Optional, Union

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


def _to_int(val: Any, default: int) -> int:
  try:
    i = int(val)
  except (TypeError, ValueError):
    return default
  return i


def _escape_md(value: Any) -> str:
  try:
    s = str(value) if value is not None else ""
  except Exception:
    s = ""
  return s.replace("|", "&#124;").replace("\n", " ")


class ListRecordsTool(Tool):
  def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
    # Parameter validation

    worksheet_id: Optional[str] = tool_parameters.get("worksheet_id")
    if not worksheet_id or not str(worksheet_id).strip():
      yield self.create_json_message({"error": "Missing parameter: worksheet_id"})
      return

    worksheet_id = str(worksheet_id).strip()

    # Pagination
    page_size = _to_int(tool_parameters.get("page_size", 50), 50)
    if page_size < 1:
      page_size = 1
    if page_size > 1000:
      page_size = 1000
    page_index = _to_int(tool_parameters.get("page_index", 1), 1)
    if page_index < 1:
      page_index = 1

    # Simple parameters
    view_id = tool_parameters.get("view_id")
    search = tool_parameters.get("search")
    include_system_fields = tool_parameters.get("include_system_fields")
    result_type = str(tool_parameters.get("result_type") or "json").strip().lower()

    # Parse JSON parameters
    fields: Optional[List[str]] = None
    field_ids_param = tool_parameters.get("field_ids")
    if field_ids_param:
      try:
        parsed = json.loads(field_ids_param) if isinstance(field_ids_param, str) else field_ids_param
        if isinstance(parsed, list):
          fields = [str(x) for x in parsed if str(x).strip()]
        else:
          yield self.create_json_message({"error": "Invalid JSON for field_ids: expecting array string"})
          return
      except Exception as e:
        yield self.create_json_message({"error": f"Invalid JSON for field_ids: {e}"})
        return

    filter_obj: Optional[Dict[str, Any]] = None
    filter_param = tool_parameters.get("filter")
    if filter_param:
      try:
        filter_obj = json.loads(filter_param) if isinstance(filter_param, str) else filter_param
      except Exception as e:
        yield self.create_json_message({"error": f"Invalid JSON for filter: {e}"})
        return

    sorts_obj: Optional[List[Dict[str, Any]]] = None
    sorts_param = tool_parameters.get("sorts")
    if sorts_param:
      try:
        parsed_sorts = json.loads(sorts_param) if isinstance(sorts_param, str) else sorts_param
        if isinstance(parsed_sorts, list):
          sorts_obj = parsed_sorts
        else:
          yield self.create_json_message({"error": "Invalid JSON for sorts: expecting array string"})
          return
      except Exception as e:
        yield self.create_json_message({"error": f"Invalid JSON for sorts: {e}"})
        return

    body: Dict[str, Any] = {
      "pageSize": page_size,
      "pageIndex": page_index,
      "includeTotalCount": True,
      "useFieldIdAsKey": True,
      "tableView": True
    }
    if view_id:
      body["viewId"] = str(view_id)
    if fields is not None:
      body["fields"] = fields
    if filter_obj is not None:
      body["filter"] = filter_obj
    if sorts_obj is not None:
      body["sorts"] = sorts_obj
    if search:
      body["search"] = str(search)
    if isinstance(include_system_fields, bool):
      body["includeSystemFields"] = include_system_fields

    # Request
    try:
      client = HapRequest(self.runtime.credentials)
      resp: Dict[str, Any] = client.post(f"/v3/app/worksheets/{worksheet_id}/rows/list", json_body=body)
    except Exception as e:
      yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
      return
    
    # Handle table result type before returning response
    if result_type == "table" and isinstance(resp, dict) and resp.get("success") is True:
      data = resp.get("data")
      table_text = self._to_markdown_table(data)
      yield self.create_json_message({"success": True, "data": table_text})
      return
      
    yield self.create_json_message(resp)
    return

  def _to_markdown_table(self, data: Dict[str, Any]) -> str:
    rows: List[Dict[str, Any]] = []
    if isinstance(data, dict):
      raw = data.get("rows") or data.get("list") or []
      if isinstance(raw, list):
        rows = [r for r in raw if isinstance(r, dict)]

    total = None
    if isinstance(data, dict):
      total = data.get("total")

    if not rows:
      count = total if isinstance(total, int) else 0
      header = "|id|\n|---|"
      return f"Found {count} rows.\n\n{header}"

    # Determine columns
    first = rows[0]
    keys = list(first.keys())
    # put 'id' first if present
    cols = ["id"] + [k for k in keys if k != "id"]

    # Build header
    header = "|" + "|".join(_escape_md(c) for c in cols) + "|\n|" + "|".join(["---"] * len(cols)) + "|"

    # Build rows
    lines: List[str] = []
    for r in rows:
      values: List[str] = []
      for c in cols:
        v = r.get(c, "")
        if isinstance(v, (dict, list)):
          try:
            v = json.dumps(v, ensure_ascii=False)
          except Exception:
            v = str(v)
        elif v is None:
          v = ""
        else:
          v = str(v)
        values.append(_escape_md(v))
      lines.append("|" + "|".join(values) + "|")

    count_display = total if isinstance(total, int) else len(rows)
    return f"Found {count_display} rows.\n\n{header}\n" + "\n".join(lines)
