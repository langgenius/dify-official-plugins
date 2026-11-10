from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, attachment_dict, jira_request, require, resolve_context, segment
from tools.outputs import with_outputs


class JiraListAttachmentsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """The files attached to an issue."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (key,) = require(tool_parameters, "issue_key")
            issue = jira_request(ctx, "GET", ctx.api(f"issue/{segment(key)}"), params={"fields": "attachment"}).json()
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = [attachment_dict(a) for a in (issue.get("fields") or {}).get("attachment") or []]
        self._out.update(attachments=result, count=len(result), success=True)
        yield self.create_json_message({"issue_key": key, "attachments": result})
        yield self.create_text_message(
            f"{key} has {len(result)} attachment(s)"
            + (": " + ", ".join(f"{a['filename']} (id {a['id']})" for a in result) if result else ".")
        )
