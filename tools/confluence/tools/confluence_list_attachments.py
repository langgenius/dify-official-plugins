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


class ConfluenceListAttachmentsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """The files attached to a page."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (page_id,) = require(tool_parameters, "page_id")
            if ctx.cloud:
                body = confluence_request(
                    ctx, "GET", ctx.v2(f"pages/{segment(page_id)}/attachments"), params={"limit": 250}
                ).json()
            else:
                body = confluence_request(
                    ctx, "GET", ctx.v1(f"content/{segment(page_id)}/child/attachment"), params={"limit": 200}
                ).json()
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = [attachment_dict(a) for a in body.get("results") or []]
        for a in result:
            a["page_id"] = a["page_id"] or page_id
        self._out.update(attachments=result, count=len(result), success=True)
        yield self.create_json_message({"page_id": page_id, "attachments": result})
        yield self.create_text_message(
            f"{len(result)} attachment(s)"
            + (": " + ", ".join(f"{a['title']} (id {a['id']})" for a in result) if result else ".")
        )
