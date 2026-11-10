from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import (
    ConfluenceAuthError,
    attachment_dict,
    confluence_request,
    require,
    resolve_context,
    segment,
)
from tools.outputs import with_outputs

# Larger files are described but not downloaded into the conversation.
MAX_DOWNLOAD = 50 * 1024 * 1024


class ConfluenceGetAttachmentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """An attachment's details and, unless download is off, the file itself."""
        download = tool_parameters.get("download") is not False
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (attachment_id,) = require(tool_parameters, "attachment_id")
            if ctx.cloud:
                meta = confluence_request(ctx, "GET", ctx.v2(f"attachments/{segment(attachment_id)}")).json()
                info = attachment_dict(meta)
                # The REST download route works with every credential mode; Confluence redirects to its
                # media store, and requests drops the Authorization header when the host changes.
                url = ctx.v1(f"content/{segment(info['page_id'])}/child/attachment/{segment(attachment_id)}/download")
            else:
                meta = confluence_request(
                    ctx, "GET", ctx.v1(f"content/{segment(attachment_id)}"), params={"expand": "container"}
                ).json()
                info = attachment_dict(meta)
                link = str((meta.get("_links") or {}).get("download") or "")
                # A relative link on the configured host only, so the token goes nowhere else.
                url = f"{ctx.base_url}{link}" if link.startswith("/") and not link.startswith("//") else ""
            content = None
            if download and info["size"] <= MAX_DOWNLOAD:
                if not url:
                    raise ConfluenceAuthError("Confluence returned no download link for this attachment.")
                content = confluence_request(ctx, "GET", url, headers={"Accept": "*/*"}, timeout=300).content
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(attachment=info, title=info["title"], success=True)
        yield self.create_json_message(info)
        if content is not None:
            yield self.create_blob_message(
                content, meta={"mime_type": info["media_type"] or "application/octet-stream", "filename": info["title"]}
            )
            yield self.create_text_message(f"Downloaded {info['title']} ({len(content)} bytes).")
        elif download:
            yield self.create_text_message(
                f"{info['title']} is {info['size']} bytes, over the {MAX_DOWNLOAD // (1024 * 1024)} MB download limit; "
                "only its details were returned."
            )
        else:
            yield self.create_text_message(f"{info['title']}: {info['size']} bytes, {info['media_type']}.")
