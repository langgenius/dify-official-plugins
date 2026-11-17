from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, file_dict, graph_request, require, resolve_site
from tools.outputs import with_outputs

_MAX_DOWNLOAD = 15 * 1024 * 1024


class DownloadFileTool(Tool):
    """Download a file from the site's document library."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            (file_id,) = require(tool_parameters, "file_id")
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            item = graph_request(ctx, "GET", ctx.drive_item(site["site_id"], file_id)).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the file: {e}")
            return
        info = file_dict(item)
        self._out.update(name=info["name"], size=info["size"], mime_type=info["mime_type"], web_url=info["web_url"])
        if info["is_folder"]:
            self._out["error"] = f"'{info['name']}' is a folder; list it with the list files tool."
            yield self.create_text_message(self._out["error"])
            return
        if info["size"] > _MAX_DOWNLOAD:
            self._out["error"] = f"'{info['name']}' is {info['size']} bytes, over the 15 MB download limit; open it with {info['web_url']}."
            yield self.create_text_message(self._out["error"])
            return
        url = item.get("@microsoft.graph.downloadUrl")
        if not url:
            yield self.create_text_message("Microsoft Graph returned no download link for this file.")
            return
        try:
            # The download URL is pre-authenticated and short-lived; it must not get the bearer token.
            response = requests.get(url, timeout=60)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Failed to download the file: {e}")
            return
        if response.status_code != 200:
            yield self.create_text_message(f"Failed to download the file: HTTP {response.status_code}.")
            return
        self._out.update(downloaded=True, success=True)
        yield self.create_blob_message(blob=response.content, meta={"file_name": info["name"], "mime_type": info["mime_type"] or "application/octet-stream"})
        yield self.create_text_message(f"Downloaded '{info['name']}' ({info['size']} bytes).")
