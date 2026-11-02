from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require, resolve_site
from tools.outputs import with_outputs


class DeleteItemTool(Tool):
    """Delete a list item; it goes to the site's recycle bin (n8n: Item > Delete)."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, item_id = require(tool_parameters, "list", "item_id")
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            graph_request(ctx, "DELETE", ctx.item(site["site_id"], list_id, item_id))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to delete the item: {e}")
            return
        self._out.update(item_id=item_id, success=True)
        yield self.create_text_message(f"Deleted item {item_id}.")
