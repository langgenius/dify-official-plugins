from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, parse_fields, require, resolve_site
from tools.outputs import with_outputs


def update_fields(ctx, site_id: str, list_id: str, item_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """PATCH an item's fields; columns left out keep their value. Returns the item's fields after the change."""
    return graph_request(ctx, "PATCH", f"{ctx.item(site_id, list_id, item_id)}/fields", json_body=fields).json()


class UpdateItemTool(Tool):
    """Change fields of a list item; columns left out keep their value (n8n: Item > Update)."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, item_id = require(tool_parameters, "list", "item_id")
            fields = parse_fields(tool_parameters.get("fields"))
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            update_fields(ctx, site["site_id"], list_id, item_id, fields)
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to update the item: {e}")
            return
        self._out.update(item_id=item_id, updated_fields=sorted(fields), success=True)
        yield self.create_text_message(f"Updated item {item_id}: {', '.join(sorted(fields))}.")
