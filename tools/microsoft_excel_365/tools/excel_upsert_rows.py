from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, require
from tools.outputs import with_outputs
from tools.sheet_rows import match_and_write, parse_records


class UpsertRowsTool(Tool):
    """
    Update the rows whose key column matches, append the others. Rows are objects keyed by the header row; columns left out of an object keep
    their current value.
    """

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, worksheet_name, key_column = require(tool_parameters, "workbook_id", "worksheet_name", "key_column")
            records = parse_records(tool_parameters.get("rows"))
            ctx = context_for(self, tool_parameters)
            updated, appended, _ = match_and_write(
                ctx, workbook_id, worksheet_name, key_column, records,
                update_all=bool(tool_parameters.get("update_all")), append=True,
            )
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to update or append rows: {e}")
            return

        self._out.update(rows_updated=updated, rows_appended=len(appended), success=True)
        yield self.create_text_message(
            f"In '{worksheet_name}': updated {updated} row(s) and appended {len(appended)} matching on '{key_column}'."
        )
        yield self.create_json_message({"rows_updated": updated, "rows_appended": len(appended), "appended_keys": appended})
