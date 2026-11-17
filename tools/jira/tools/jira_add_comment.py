from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import (
    JiraAuthError,
    comment_dict,
    jira_request,
    require,
    resolve_context,
    rich_text,
    segment,
)
from tools.outputs import with_outputs


class JiraAddCommentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Add a comment (Markdown) to an issue."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            key, text = require(tool_parameters, "issue_key", "comment")
            comment = jira_request(
                ctx, "POST", ctx.api(f"issue/{segment(key)}/comment"), json_body={"body": rich_text(ctx, text)}
            ).json()
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = comment_dict(comment)
        self._out.update(comment_id=result["id"], issue_key=key, success=True)
        yield self.create_json_message({"issue_key": key, "comment": result})
        yield self.create_text_message(f"Added comment {result['id']} to {key}.")
