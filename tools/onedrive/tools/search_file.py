from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, file_info, graph_request, resolve_graph_context


class SearchFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        query = tool_parameters.get("query")
        limit = tool_parameters.get("limit", 10)

        if not query:
            yield self.create_text_message("Query parameter is required.")
            yield self.create_json_message({"error": "Query parameter is required."})
            return
        try:
            limit = max(int(limit or 10), 1)
        except (TypeError, ValueError):
            limit = 10

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"))
            # The search text is an OData string literal inside the path: double single quotes, then URL-quote.
            q = quote(str(query).replace("'", "''"), safe="")
            response = graph_request(graph, "GET", f"{graph.drive_base}/root/search(q='{q}')", params={"$top": limit})
        except GraphAuthError as e:
            yield self.create_text_message(f"Error searching files: {e}")
            yield self.create_json_message({"error": str(e)})
            return

        files = (response.json().get("value") or [])[:limit]
        yield self.create_json_message({"results": [file_info(f) for f in files]})
