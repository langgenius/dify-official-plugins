from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, item_dict, require, resolve_site
from tools.outputs import with_outputs


class GetItemTool(Tool):
    """One list item with its fields."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, item_id = require(tool_parameters, "list", "item_id")
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            item = item_dict(graph_request(ctx, "GET", ctx.item(site["site_id"], list_id, item_id), params={"$expand": "fields"}).json())
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the item: {e}")
            return
        self._out.update(item, success=True)
        yield self.create_text_message(str(item["fields"]))
        yield self.create_json_message(item)
