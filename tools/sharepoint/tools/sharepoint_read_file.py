from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, file_dict, graph_request, require, resolve_site
from tools.outputs import with_outputs
from tools.text_extract import UnreadableFile, extract_text, kind_of

_MAX_DOWNLOAD = 15 * 1024 * 1024
_DEFAULT_CHARS = 20_000
_MAX_CHARS = 200_000


class ReadFileTool(Tool):
    """
    The text of a file in the site's document library: plain text, Word, Excel, PowerPoint or PDF.
    Unlike download file it returns text, not a file, so agents can read documents.
    """

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            (file_id,) = require(tool_parameters, "file_id")
            max_chars = int(tool_parameters.get("max_chars") or _DEFAULT_CHARS)
        except (GraphAuthError, ValueError) as e:
            yield self.create_text_message(f"Failed to read the file: {e}")
            return
        max_chars = max(1, min(max_chars, _MAX_CHARS))
        try:
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            item = graph_request(ctx, "GET", ctx.drive_item(site["site_id"], file_id)).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the file: {e}")
            return
        info = file_dict(item)
        self._out.update(name=info["name"], mime_type=info["mime_type"], web_url=info["web_url"])
        kind = None if info["is_folder"] else kind_of(info["name"], info["mime_type"])
        if info["is_folder"]:
            self._out["error"] = f"'{info['name']}' is a folder; list it with the list files tool."
        elif kind is None:
            self._out["error"] = (
                f"'{info['name']}' ({info['mime_type'] or 'unknown type'}) cannot be read as text. "
                "Text, Word, Excel, PowerPoint and PDF files can; in a workflow, download it with the download file tool."
            )
        elif info["size"] > _MAX_DOWNLOAD:
            self._out["error"] = f"'{info['name']}' is {info['size']} bytes, over the 15 MB limit; open it with {info['web_url']}."
        if self._out.get("error"):
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
        try:
            text = extract_text(kind, response.content)
        except UnreadableFile as e:
            self._out["error"] = f"'{info['name']}': {e}."
            yield self.create_text_message(self._out["error"])
            return
        truncated = len(text) > max_chars
        content = text[:max_chars]
        self._out.update(content=content, length=len(text), truncated=truncated, success=True)
        note = f"\n\n[Truncated: showing {max_chars} of {len(text)} characters.]" if truncated else ""
        yield self.create_text_message(f"# {info['name']}\n\n{content}{note}")
