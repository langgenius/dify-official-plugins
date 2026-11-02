from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, item_dict, parse_fields, require, resolve_site
from tools.outputs import with_outputs


class CreateItemTool(Tool):
    """Add an item to a list (n8n: Item > Create)."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            (list_id,) = require(tool_parameters, "list")
            fields = parse_fields(tool_parameters.get("fields"))
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            item = item_dict(graph_request(ctx, "POST", ctx.items(site["site_id"], list_id), json_body={"fields": fields}).json())
        except GraphAuthError as e:
            hint = " Column names are the internal names; get them with the get list tool." if "400" in str(e) else ""
            yield self.create_text_message(f"Failed to create the item: {e}{hint}")
            return
        self._out.update(item, success=True)
        yield self.create_text_message(f"Created item {item['item_id']}.")
        yield self.create_json_message(item)
