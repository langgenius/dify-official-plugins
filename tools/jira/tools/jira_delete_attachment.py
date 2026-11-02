from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, jira_request, require, resolve_context, segment
from tools.outputs import with_outputs


class JiraDeleteAttachmentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Delete an attachment from its issue."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (attachment_id,) = require(tool_parameters, "attachment_id")
            jira_request(ctx, "DELETE", ctx.api(f"attachment/{segment(attachment_id)}"))
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(deleted=True, success=True)
        yield self.create_json_message({"attachment_id": attachment_id, "deleted": True})
        yield self.create_text_message(f"Deleted attachment {attachment_id}.")
