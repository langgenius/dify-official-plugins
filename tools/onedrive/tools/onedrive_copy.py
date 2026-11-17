import time
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.outputs import with_outputs
from tools.graph_client import GraphAuthError, graph_request, item_url, item_vars, resolve_graph_context, segment

# OneDrive copies in the background; wait this long for small copies to finish.
_WAIT_SECONDS = 15


class CopyTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Copy a file or folder into a folder of the same drive, optionally
        under a new name. A name already taken in the target folder gets a number appended.
        """
        file_id = str(tool_parameters.get("file_id") or "").strip()
        name = str(tool_parameters.get("name") or "").strip()
        parent_id = str(tool_parameters.get("parent_folder_id") or "").strip()
        if not file_id:
            yield self.create_text_message("File ID is required.")
            return

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"), tool=self)
            source = graph_request(graph, "GET", f"{graph.drive_base}/items/{segment(file_id)}").json()
            source_parent = source.get("parentReference") or {}
            if parent_id:
                target = graph_request(graph, "GET", item_url(graph, parent_id), params={"$select": "id,parentReference"}).json()
                parent_ref = {"driveId": (target.get("parentReference") or {}).get("driveId") or source_parent.get("driveId"), "id": target["id"]}
            else:
                parent_ref = {"driveId": source_parent.get("driveId"), "id": source_parent.get("id")}
            body: dict[str, Any] = {"parentReference": {k: v for k, v in parent_ref.items() if v}}
            if name:
                body["name"] = name
            response = graph_request(
                graph,
                "POST",
                f"{graph.drive_base}/items/{segment(file_id)}/copy",
                params={"@microsoft.graph.conflictBehavior": "rename"},
                json=body,
            )
            monitor = response.headers.get("Location", "")
            status, new_id = self._wait(monitor)
            copy = graph_request(graph, "GET", f"{graph.drive_base}/items/{segment(new_id)}").json() if new_id else {}
        except GraphAuthError as e:
            yield self.create_text_message(f"Error copying: {e}")
            return

        if status == "failed":
            self._out["error"] = "OneDrive reported that the copy failed."
            yield self.create_text_message("OneDrive reported that the copy failed.")
            return
        v = item_vars(copy) if copy else {"id": "", "name": name or source.get("name", ""), "web_url": ""}
        self._out.update(file_id=v["id"], name=v["name"], web_url=v["web_url"], status=status, success=True)
        if status == "completed":
            yield self.create_text_message(f"Copied to '{v['name']}' (id: {v['id']}) {v['web_url']}".strip())
        else:
            yield self.create_text_message(
                f"The copy of '{source.get('name', file_id)}' was started and is still running in OneDrive "
                "(large items take a while); it will appear in the target folder when done."
            )
        yield self.create_json_message({"file_id": v["id"], "name": v["name"], "web_url": v["web_url"], "status": status})

    @staticmethod
    def _wait(monitor: str) -> tuple[str, str]:
        """
        Poll the copy's monitor URL. It is pre-authenticated and on another host, so it
        must not get the bearer token. Returns (status, new item ID once completed).
        """
        if not monitor.startswith("https://"):
            return "in_progress", ""
        deadline = time.monotonic() + _WAIT_SECONDS
        while True:
            try:
                body = requests.get(monitor, timeout=15, allow_redirects=False).json()
            except (requests.exceptions.RequestException, ValueError):
                return "in_progress", ""
            status = str(body.get("status") or "")
            if status == "completed":
                return "completed", str(body.get("resourceId") or "")
            if status == "failed":
                return "failed", ""
            if time.monotonic() > deadline:
                return "in_progress", ""
            time.sleep(1)
