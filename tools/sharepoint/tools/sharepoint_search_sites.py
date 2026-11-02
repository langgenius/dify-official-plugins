from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, get_all, site_dict
from tools.outputs import with_outputs


class SearchSitesTool(Tool):
    """Find SharePoint sites by name (n8n's site picker)."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        query = str(tool_parameters.get("query") or "").strip() or "*"
        try:
            limit = max(1, min(int(tool_parameters.get("limit") or 20), 200))
            ctx = context_for(self, tool_parameters)
            sites = [site_dict(s) for s in get_all(ctx, f"{ctx.api_base}/sites", {"search": query, "$top": min(limit, 100)}, limit)]
        except (GraphAuthError, ValueError) as e:
            yield self.create_text_message(f"Failed to search sites: {e}")
            return
        self._out.update(sites=sites, count=len(sites), success=True)
        if not sites:
            yield self.create_text_message(f"No sites found for '{query}'.")
            return
        yield self.create_text_message(
            f"{len(sites)} site(s):\n" + "\n".join(f"- {s['name']} ({s['web_url']}, id: {s['site_id']})" for s in sites)
        )
        yield self.create_json_message({"sites": sites, "count": len(sites)})
