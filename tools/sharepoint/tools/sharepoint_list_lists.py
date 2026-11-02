from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, get_all, list_dict, resolve_site
from tools.outputs import with_outputs


class ListListsTool(Tool):
    """The lists and document libraries of a site (n8n: List > Get Many)."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        include_hidden = bool(tool_parameters.get("include_hidden"))
        try:
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            lists = [list_dict(item) for item in get_all(
                ctx, ctx.lists(site["site_id"]), {"$select": "id,name,displayName,description,webUrl,list"}, 1000)]
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to list the site's lists: {e}")
            return
        if not include_hidden:
            lists = [item for item in lists if not item["hidden"]]
        self._out.update(lists=lists, count=len(lists), site_id=site["site_id"], success=True)
        yield self.create_text_message(
            f"{len(lists)} list(s) in '{site['name']}':\n"
            + "\n".join(f"- {item['name']} ({item['template']}, id: {item['list_id']})" for item in lists)
        )
        yield self.create_json_message({"site_id": site["site_id"], "lists": lists, "count": len(lists)})
