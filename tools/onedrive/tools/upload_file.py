from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File

from tools.outputs import with_outputs
from tools.graph_client import file_info, graph_request, GraphAuthError, item_vars, resolve_graph_context


class UploadFileTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file: File = tool_parameters.get("file")
        custom_file_name = tool_parameters.get("file_name")

        if not file:
            yield self.create_text_message("File is required.")
            yield self.create_json_message({"error": "File is required."})
            return

        file_content = file.blob
        original_file_name = file.filename

        file_name = custom_file_name if custom_file_name else original_file_name

        if not file_content:
            yield self.create_text_message("File content is empty.")
            yield self.create_json_message({"error": "File content is empty."})
            return

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"))
            # Simple upload relative to the drive root; "/" in the name selects a folder path.
            path = quote(str(file_name).strip().lstrip("/"), safe="/")
            uploaded = graph_request(
                graph,
                "PUT",
                f"{graph.drive_base}/root:/{path}:/content",
                data=file_content,
                headers={"Content-Type": "application/octet-stream"},
                timeout=300,
            ).json()
        except GraphAuthError as e:
            error_message = f"Error uploading file: {e}"
            yield self.create_text_message(error_message)
            yield self.create_json_message({"error": error_message})
            return

        info = file_info(uploaded)
        v = item_vars(uploaded)
        self._out.update(file_id=v["id"], name=v["name"], size=v["size"], web_url=v["web_url"], success=True)
        yield self.create_text_message(f"File uploaded successfully: {info}")
        yield self.create_json_message(info)
