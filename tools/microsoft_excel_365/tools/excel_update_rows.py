from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, require
from tools.outputs import with_outputs
from tools.sheet_rows import match_and_write, parse_records


class UpdateRowsTool(Tool):
    """
    Update the rows whose key column matches. Rows are
    objects keyed by the header row; columns left out keep their value. Nothing is appended:
    keys with no matching row are reported.
    """

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, worksheet_name, key_column = require(tool_parameters, "workbook_id", "worksheet_name", "key_column")
            records = parse_records(tool_parameters.get("rows"))
            ctx = context_for(self, tool_parameters)
            updated, _, missing = match_and_write(
                ctx, workbook_id, worksheet_name, key_column, records,
                update_all=bool(tool_parameters.get("update_all")), append=False,
            )
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to update rows: {e}")
            return

        self._out.update(rows_updated=updated, not_found=missing, success=True)
        text = f"In '{worksheet_name}': updated {updated} row(s) matching on '{key_column}'."
        if missing:
            text += f" No row has {key_column} = {', '.join(missing)}; nothing was added for those."
        yield self.create_text_message(text)
        yield self.create_json_message({"rows_updated": updated, "not_found": missing})
