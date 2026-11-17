from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, require, resolve_context
from tools.jira_fields import list_transitions
from tools.outputs import with_outputs


class JiraListTransitionsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """The workflow transitions the current account can make on an issue right now."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (key,) = require(tool_parameters, "issue_key")
            transitions = list_transitions(ctx, key)
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(transitions=transitions, success=True)
        yield self.create_json_message({"issue_key": key, "transitions": transitions})
        yield self.create_text_message(
            f"{key} can move to: " + ", ".join(f"{t['to_status']} (via '{t['name']}', id {t['id']})" for t in transitions)
            if transitions
            else f"No transitions are available on {key} for this account."
        )
