from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, confluence_request, require, resolve_context, segment
from tools.outputs import with_outputs


class ConfluenceDeleteCommentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Delete a footer comment."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (comment_id,) = require(tool_parameters, "comment_id")
            url = ctx.v2(f"footer-comments/{segment(comment_id)}") if ctx.cloud else ctx.v1(f"content/{segment(comment_id)}")
            confluence_request(ctx, "DELETE", url)
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(deleted=True, success=True)
        yield self.create_json_message({"comment_id": comment_id, "deleted": True})
        yield self.create_text_message(f"Deleted comment {comment_id}.")
