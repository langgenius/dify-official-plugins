from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.outputs import with_outputs
from tools.graph_client import GraphAuthError, graph_request, item_vars, resolve_graph_context, segment

# Characters OneDrive does not allow in file and folder names.
_INVALID = set('"*:<>?/\\|')


class RenameTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Rename a file or folder."""
        item_id = str(tool_parameters.get("item_id") or "").strip()
        new_name = str(tool_parameters.get("new_name") or "").strip()
        if not item_id or not new_name:
            yield self.create_text_message("Item ID and New Name are required.")
            return
        if _INVALID & set(new_name):
            yield self.create_text_message('The new name cannot contain any of these characters: " * : < > ? / \\ |')
            return

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"), tool=self)
            item = graph_request(graph, "PATCH", f"{graph.drive_base}/items/{segment(item_id)}", json={"name": new_name}).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Error renaming: {e}")
            return

        v = item_vars(item)
        self._out.update(file_id=v["id"], name=v["name"], is_folder=v["is_folder"], web_url=v["web_url"], success=True)
        yield self.create_text_message(f"Renamed to '{v['name']}' (id: {v['id']}).")
        yield self.create_json_message({"file_id": v["id"], "name": v["name"], "is_folder": v["is_folder"], "web_url": v["web_url"]})
