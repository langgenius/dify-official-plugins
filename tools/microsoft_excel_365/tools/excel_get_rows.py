from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs
from tools.sheet_rows import as_records

_MAX_ROWS = 5000


def _index(value: Any, default: int, name: str) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as e:
        raise GraphAuthError(f"{name} must be a whole number (0 is the first row).") from e
    if number < 0:
        raise GraphAuthError(f"{name} must be 0 or more (0 is the first row).")
    return number


class GetRowsTool(Tool):
    """
    Rows of a worksheet as objects keyed by its header row.
    Without a range, the sheet's used range is read.
    """

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        range_address = str(tool_parameters.get("range") or "").strip()
        try:
            workbook_id, worksheet_name = require(tool_parameters, "workbook_id", "worksheet_name")
            header_row = _index(tool_parameters.get("header_row"), 0, "header_row")
            first_data_row = _index(tool_parameters.get("first_data_row"), header_row + 1, "first_data_row")
            if first_data_row <= header_row:
                raise GraphAuthError("first_data_row must come after header_row.")
            limit = max(1, min(_index(tool_parameters.get("limit"), 500, "limit") or 500, _MAX_ROWS))
            ctx = context_for(self, tool_parameters)
            url = ctx.range(workbook_id, worksheet_name, range_address) if range_address else ctx.used_range(workbook_id, worksheet_name)
            data = graph_request(ctx, "GET", url).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get rows: {e}")
            return

        values = data.get("values") or []
        address = data.get("address", "")
        if len(values) <= header_row or all(str(c) == "" for c in values[header_row]):
            self._out.update(rows=[], columns=[], count=0, has_more=False, address=address, success=True)
            yield self.create_text_message(f"'{worksheet_name}' has no header row at {address or 'the start of the data'}.")
            return
        header = values[header_row]
        # Rows with no value at all (e.g. gaps left by cleared cells) are skipped.
        data_rows = [row for row in values[first_data_row:] if any(str(c) != "" for c in row)]
        has_more = len(data_rows) > limit
        records = as_records(header, data_rows[:limit])
        columns = [str(h) for h in header]
        self._out.update(rows=records, columns=columns, count=len(records), has_more=has_more, address=address, success=True)
        more = f" (more rows exist; raise the limit, up to {_MAX_ROWS})" if has_more else ""
        yield self.create_text_message(
            f"{len(records)} row(s) from '{worksheet_name}' ({address}), columns: {', '.join(columns)}{more}."
        )
        yield self.create_json_message({"columns": columns, "rows": records, "count": len(records), "has_more": has_more, "address": address})
