from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, confluence_request, require, resolve_context, segment
from tools.outputs import with_outputs


class ConfluenceGetLabelsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """A page's labels."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (page_id,) = require(tool_parameters, "page_id")
            if ctx.cloud:
                body = confluence_request(ctx, "GET", ctx.v2(f"pages/{segment(page_id)}/labels"), params={"limit": 250}).json()
            else:
                body = confluence_request(ctx, "GET", ctx.v1(f"content/{segment(page_id)}/label"), params={"limit": 200}).json()
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        labels = [label.get("name", "") for label in body.get("results") or []]
        self._out.update(labels=labels, success=True)
        yield self.create_json_message({"page_id": page_id, "labels": labels})
        yield self.create_text_message(f"Labels: {', '.join(labels)}" if labels else "The page has no labels.")
