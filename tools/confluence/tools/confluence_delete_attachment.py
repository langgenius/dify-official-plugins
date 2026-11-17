from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, confluence_request, require, resolve_context, segment
from tools.outputs import with_outputs


class ConfluenceDeleteAttachmentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Delete an attachment (it goes to the space's trash)."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (attachment_id,) = require(tool_parameters, "attachment_id")
            url = ctx.v2(f"attachments/{segment(attachment_id)}") if ctx.cloud else ctx.v1(f"content/{segment(attachment_id)}")
            confluence_request(ctx, "DELETE", url)
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(deleted=True, success=True)
        yield self.create_json_message({"attachment_id": attachment_id, "deleted": True})
        yield self.create_text_message(f"Deleted attachment {attachment_id}.")
