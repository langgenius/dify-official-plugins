from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class AddTableTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        has_headers = tool_parameters.get("has_headers")
        has_headers = True if has_headers is None else bool(has_headers)
        name = str(tool_parameters.get("table_name") or "").strip()
        try:
            workbook_id, worksheet_name, range_address = require(tool_parameters, "workbook_id", "worksheet_name", "range")
            ctx = context_for(self, tool_parameters)
            address = range_address if "!" in range_address else f"'{worksheet_name.replace(chr(39), chr(39) * 2)}'!{range_address}"
            table = graph_request(
                ctx, "POST", f"{ctx.workbook(workbook_id)}/tables/add", json_body={"address": address, "hasHeaders": has_headers}
            ).json()
            if name:
                table = graph_request(ctx, "PATCH", ctx.table(workbook_id, table["id"]), json_body={"name": name}).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to add the table: {e}")
            return
        self._out.update(table_id=table.get("id", ""), name=table.get("name", ""), success=True)
        yield self.create_text_message(f"Added table '{table.get('name', '')}' on {address} (id: {table.get('id', '')}).")
        yield self.create_json_message({"table_id": table.get("id", ""), "name": table.get("name", ""), "address": address})
