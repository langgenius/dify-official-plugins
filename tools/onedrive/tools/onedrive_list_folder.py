from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.outputs import with_outputs
from tools.graph_client import GraphAuthError, graph_request, item_url, item_vars, resolve_graph_context

_MAX_LIMIT = 200


class ListFolderTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """The items in a folder; no folder ID means the root."""
        folder_id = str(tool_parameters.get("folder_id") or "").strip()
        try:
            limit = int(tool_parameters.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, _MAX_LIMIT))

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"), tool=self)
            url: str | None = f"{item_url(graph, folder_id)}/children"
            params: dict[str, Any] | None = {"$top": min(limit, 100)}
            items: list[dict[str, Any]] = []
            while url and len(items) < limit:
                body = graph_request(graph, "GET", url, params=params).json()
                items.extend(body.get("value", []))
                url = body.get("@odata.nextLink")
                params = None  # the next link carries the query
                # Follow only Graph's own links, so the token never goes elsewhere.
                if url and not url.startswith(graph.api_base + "/"):
                    url = None
        except GraphAuthError as e:
            yield self.create_text_message(f"Error listing the folder: {e}")
            return

        has_more = bool(url) or len(items) > limit
        items = items[:limit]
        flat = [item_vars(item) for item in items]
        self._out.update(items=flat, count=len(flat), has_more=has_more, success=True)

        where = f"folder {folder_id}" if folder_id and folder_id != "root" else "the root folder"
        if not flat:
            yield self.create_text_message(f"{where[0].upper()}{where[1:]} is empty.")
        else:
            lines = [
                f"- {v['name']} ({'folder' if v['is_folder'] else f'{v['size']} bytes'}, id: {v['id']})" for v in flat
            ]
            more = "\nThere are more items; raise the limit to see them." if has_more else ""
            yield self.create_text_message(f"{len(flat)} item(s) in {where}:\n" + "\n".join(lines) + more)
        yield self.create_json_message({"items": flat, "count": len(flat), "has_more": has_more})
