from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, resolve_site
from tools.outputs import with_outputs


class GetSiteTool(Tool):
    """A site from its URL, its ID or "root"; returns the ID the other tools take."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the site: {e}")
            return
        self._out.update(site, success=True)
        yield self.create_text_message(f"Site '{site['name']}' ({site['web_url']}), id: {site['site_id']}")
        yield self.create_json_message(site)
