from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, jira_request, require, resolve_context, rich_text, segment
from tools.jira_fields import list_transitions, match_transition
from tools.outputs import with_outputs


class JiraTransitionIssueTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Move an issue through its workflow (change its status), optionally with a comment."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            key, wanted = require(tool_parameters, "issue_key", "transition")
            transition = match_transition(list_transitions(ctx, key), wanted)
            body: dict[str, Any] = {"transition": {"id": transition["id"]}}
            comment = str(tool_parameters.get("comment") or "").strip()
            if comment:
                body["update"] = {"comment": [{"add": {"body": rich_text(ctx, comment)}}]}
            jira_request(ctx, "POST", ctx.api(f"issue/{segment(key)}/transitions"), json_body=body)
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(issue_key=key, status=transition["to_status"], transition_id=transition["id"], success=True)
        yield self.create_json_message({"issue_key": key, "status": transition["to_status"], "transition": transition})
        yield self.create_text_message(f"Moved {key} to {transition['to_status']}.")
