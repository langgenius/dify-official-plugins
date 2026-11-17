from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from tools.confluence_client import (
    ConfluenceAuthError,
    attachment_dict,
    confluence_request,
    require,
    resolve_context,
    segment,
)
from tools.outputs import with_outputs


class ConfluenceUploadAttachmentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Attach a file (or text written by the agent) to a page."""
        file: File | None = tool_parameters.get("file")
        file_name = str(tool_parameters.get("file_name") or "").strip()
        text = tool_parameters.get("file_content")
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (page_id,) = require(tool_parameters, "page_id")
            if file:
                content, name, mime = file.blob, file_name or file.filename, file.mime_type
            elif text:
                if not file_name:
                    raise ConfluenceAuthError("A file name (such as notes.txt) is required when attaching text.")
                content, name, mime = str(text).encode("utf-8"), file_name, "text/plain"
            else:
                raise ConfluenceAuthError("A file or some text content is required.")
            if not content:
                raise ConfluenceAuthError("The file is empty.")
            files: dict[str, Any] = {"file": (name or "attachment", content, mime or "application/octet-stream")}
            comment = str(tool_parameters.get("comment") or "").strip()
            if comment:
                files["comment"] = (None, comment)
            body = confluence_request(
                ctx, "POST", ctx.v1(f"content/{segment(page_id)}/child/attachment"),
                files=files,
                # Confluence requires this header on multipart uploads (XSRF protection).
                headers={"X-Atlassian-Token": "no-check"},
                timeout=300,
            ).json()
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        uploaded = [attachment_dict(a) for a in body.get("results") or []]
        first = uploaded[0] if uploaded else {"id": "", "title": name, "size": len(content)}
        first["size"] = first.get("size") or len(content)
        self._out.update(attachment_id=first["id"], title=first["title"], size=first["size"], success=True)
        yield self.create_json_message({"page_id": page_id, "attachments": uploaded})
        yield self.create_text_message(f"Attached {first['title']} to page {page_id}.")
