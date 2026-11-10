from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.outputs import with_outputs
from tools.graph_client import GraphAuthError, find_child, graph_request, item_url, item_vars, resolve_graph_context


class CreateFolderTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Create a folder. The name may be a path such as
        "Pictures/2021": missing folders along it are created, existing ones reused.
        """
        name = str(tool_parameters.get("name") or "").strip().strip("/")
        parent_id = str(tool_parameters.get("parent_folder_id") or "").strip()
        parts = [part.strip() for part in name.split("/") if part.strip()]
        if not parts:
            yield self.create_text_message("Folder name is required.")
            return
        if any(part in (".", "..") for part in parts):
            yield self.create_text_message("The folder name cannot contain '.' or '..' segments.")
            return

        created = False
        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"), tool=self)
            folder: dict[str, Any] = {}
            current = parent_id
            for part in parts:
                existing = find_child(graph, current, part)
                if existing is not None:
                    if "folder" not in existing:
                        raise GraphAuthError(f"'{part}' already exists and is a file, not a folder.")
                    folder, created = existing, False
                else:
                    folder = graph_request(
                        graph,
                        "POST",
                        f"{item_url(graph, current)}/children",
                        json={"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
                    ).json()
                    created = True
                current = folder.get("id", "")
        except GraphAuthError as e:
            yield self.create_text_message(f"Error creating the folder: {e}")
            return

        v = item_vars(folder)
        self._out.update(folder_id=v["id"], name=v["name"], web_url=v["web_url"], created=created, success=True)
        state = "Created" if created else "Already existed:"
        yield self.create_text_message(f"{state} folder '{'/'.join(parts)}' (id: {v['id']}) {v['web_url']}".strip())
        yield self.create_json_message({"folder_id": v["id"], "name": v["name"], "web_url": v["web_url"], "created": created})
