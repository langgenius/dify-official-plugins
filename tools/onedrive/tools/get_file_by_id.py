from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.outputs import with_outputs
from tools.graph_client import file_info, graph_request, GraphAuthError, item_vars, resolve_graph_context, segment

_MAX_DOWNLOAD = 15 * 1024 * 1024


class GetFileByIdTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        file_id = tool_parameters.get("file_id")
        download = tool_parameters.get("download", False)

        if not file_id:
            yield self.create_text_message("File ID is required.")
            yield self.create_json_message({"error": "File ID is required."})
            return

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"))
            item = graph_request(graph, "GET", f"{graph.drive_base}/items/{segment(file_id)}").json()
        except GraphAuthError as e:
            yield self.create_json_message({"error": str(e)})
            yield self.create_text_message(f"Error retrieving file: {e}")
            return

        info = file_info(item)
        v = item_vars(item)
        self._out.update(
            file_id=v["id"], name=v["name"], is_folder=v["is_folder"], mime_type=v["mime_type"],
            size=v["size"], web_url=v["web_url"], download_url=v["download_url"], success=True,
        )
        yield self.create_json_message(info)
        if download and info.get("download_url") and (info.get("size") or 0) < _MAX_DOWNLOAD:
            # The download URL is pre-authenticated and short-lived; it must not get the bearer token.
            try:
                response = requests.get(info["download_url"], timeout=30)
            except requests.exceptions.RequestException as e:
                self._out.update(success=False, error=f"Error downloading file: {e}")
                yield self.create_text_message(f"Error downloading file: {e}")
                return
            if response.status_code == 200:
                self._out["downloaded"] = True
                yield self.create_blob_message(blob=response.content, meta={"file_name": info["name"]})
