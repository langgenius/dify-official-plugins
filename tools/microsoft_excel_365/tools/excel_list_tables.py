from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class ListTablesTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            (workbook_id,) = require(tool_parameters, "workbook_id")
            ctx = context_for(self, tool_parameters)
            data = graph_request(ctx, "GET", f"{ctx.workbook(workbook_id)}/tables", params={"$expand": "worksheet($select=name)"}).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to list tables: {e}")
            return
        tables = [
            {"id": t.get("id", ""), "name": t.get("name", ""), "worksheet": (t.get("worksheet") or {}).get("name", ""),
             "show_headers": bool(t.get("showHeaders", True))}
            for t in data.get("value", [])
        ]
        self._out.update(tables=tables, count=len(tables), success=True)
        if not tables:
            yield self.create_text_message("The workbook has no tables.")
            return
        yield self.create_text_message(
            f"{len(tables)} table(s):\n" + "\n".join(f"- {t['name']} on '{t['worksheet']}' (id: {t['id']})" for t in tables)
        )
        yield self.create_json_message({"tables": tables, "count": len(tables)})
