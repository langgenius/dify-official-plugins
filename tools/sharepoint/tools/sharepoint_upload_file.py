from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, file_dict, graph_request, resolve_site
from tools.outputs import with_outputs


class UploadFileTool(Tool):
    """
    Upload a file, or save text as a file, into a folder of the site's document library
    (n8n: File > Upload). A file with the same name is replaced.
    """

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file = tool_parameters.get("file")
        text = tool_parameters.get("file_content")
        name = str(tool_parameters.get("file_name") or "").strip()
        folder_id = str(tool_parameters.get("folder_id") or "").strip()
        try:
            if file:
                content, name = file.blob, name or file.filename
            elif text:
                if not name:
                    raise GraphAuthError("A file name (such as notes.txt) is required when uploading text.")
                content = str(text).encode("utf-8")
            else:
                raise GraphAuthError("A file or some text content is required.")
            if not content:
                raise GraphAuthError("The file is empty.")
            if any(part in (".", "..") for part in name.split("/")):
                raise GraphAuthError("The file name cannot contain '.' or '..' segments.")
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            path = quote(name.strip("/"), safe="/")
            uploaded = graph_request(
                ctx, "PUT", f"{ctx.drive_item(site['site_id'], folder_id)}:/{path}:/content",
                data=content, headers={"Content-Type": "application/octet-stream"}, timeout=300,
            ).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to upload the file: {e}")
            return
        info = file_dict(uploaded)
        self._out.update(file_id=info["id"], name=info["name"], size=info["size"], web_url=info["web_url"], success=True)
        yield self.create_text_message(f"Uploaded '{info['name']}' ({info['size']} bytes): {info['web_url']}")
        yield self.create_json_message(info)
