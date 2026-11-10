from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File

from tools.outputs import with_outputs
from tools.graph_client import file_info, graph_request, GraphAuthError, item_url, item_vars, resolve_graph_context


class UploadFileTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file: File | None = tool_parameters.get("file")
        custom_file_name = tool_parameters.get("file_name")
        text_content = tool_parameters.get("file_content")
        parent_id = str(tool_parameters.get("parent_folder_id") or "").strip()

        if file:
            file_content = file.blob
            file_name = custom_file_name if custom_file_name else file.filename
        elif text_content:
            # Text written by the agent or a workflow, saved as a UTF-8 file.
            if not custom_file_name:
                yield self.create_text_message("A file name (such as notes.txt) is required when uploading text.")
                yield self.create_json_message({"error": "A file name is required when uploading text."})
                return
            file_content = str(text_content).encode("utf-8")
            file_name = custom_file_name
        else:
            yield self.create_text_message("A file or some text content is required.")
            yield self.create_json_message({"error": "A file or some text content is required."})
            return

        if not file_content:
            yield self.create_text_message("File content is empty.")
            yield self.create_json_message({"error": "File content is empty."})
            return

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"), tool=self)
            # Simple upload relative to the drive root (or the given folder); "/" in the name selects a folder path.
            path = quote(str(file_name).strip().lstrip("/"), safe="/")
            uploaded = graph_request(
                graph,
                "PUT",
                f"{item_url(graph, parent_id)}:/{path}:/content",
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
