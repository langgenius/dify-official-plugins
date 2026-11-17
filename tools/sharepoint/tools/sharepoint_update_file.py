from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, file_dict, graph_request, require, resolve_site
from tools.outputs import with_outputs

_INVALID = set('"*:<>?/\\|')


class UpdateFileTool(Tool):
    """Rename a file and/or replace its content."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        new_name = str(tool_parameters.get("new_name") or "").strip()
        file = tool_parameters.get("file")
        renamed = False
        try:
            (file_id,) = require(tool_parameters, "file_id")
            if not new_name and not file:
                raise GraphAuthError("Nothing to update: give a new name, a new file content, or both.")
            if new_name and _INVALID & set(new_name):
                raise GraphAuthError('The new name cannot contain any of these characters: " * : < > ? / \\ |')
            if file and not file.blob:
                raise GraphAuthError("The new file is empty.")
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            url = ctx.drive_item(site["site_id"], file_id)
            item = None
            if new_name:
                item = graph_request(ctx, "PATCH", url, json_body={"name": new_name}).json()
                renamed = True
            if file:
                item = graph_request(ctx, "PUT", f"{url}/content", data=file.blob,
                                     headers={"Content-Type": "application/octet-stream"}, timeout=300).json()
        except GraphAuthError as e:
            note = " The file was renamed; run again without a new name to retry the content." if renamed else ""
            yield self.create_text_message(f"Failed to update the file: {e}{note}")
            return
        info = file_dict(item or {})
        self._out.update(file_id=info["id"], name=info["name"], size=info["size"], web_url=info["web_url"], success=True)
        done = " and ".join(x for x, on in (("renamed", bool(new_name)), ("replaced its content", bool(file))) if on)
        yield self.create_text_message(f"Updated '{info['name']}': {done}.")
        yield self.create_json_message(info)
