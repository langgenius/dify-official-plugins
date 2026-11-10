from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, jira_request, require, resolve_context, segment
from tools.jira_fields import split_list
from tools.outputs import with_outputs

ROLES = ("reporter", "assignee", "watchers", "voters")


class JiraNotifyIssueTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Email people about an issue through Jira's own notification."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            key, subject, text = require(tool_parameters, "issue_key", "subject", "text")
            roles = [r.lower() for r in split_list(tool_parameters.get("recipients") or "watchers")]
            unknown = [r for r in roles if r not in ROLES]
            if unknown:
                raise JiraAuthError(f"Unknown recipients {unknown}; use any of: {', '.join(ROLES)}.")
            users = split_list(tool_parameters.get("user_ids"))
            to: dict[str, Any] = {role: role in roles for role in ROLES}
            if users:
                to["users"] = [{"accountId": u} if ctx.cloud else {"name": u} for u in users]
            body: dict[str, Any] = {"subject": subject, "textBody": text, "to": to}
            jira_request(ctx, "POST", ctx.api(f"issue/{segment(key)}/notify"), json_body=body)
        except JiraAuthError as e:
            message = str(e)
            if "No recipients" in message:
                message = (
                    f"Jira found nobody to notify about {key}: the chosen recipients ({', '.join(roles) or 'none'}) "
                    "are empty or are only the signed-in account, and Jira never emails the sender. "
                    "Pick other recipients or give user_ids."
                )
            yield self.create_text_message(message)
            return
        self._out.update(issue_key=key, success=True)
        who = ", ".join(roles + ([f"{len(users)} user(s)"] if users else []))
        yield self.create_json_message({"issue_key": key, "notified": who})
        yield self.create_text_message(
            f"Jira is sending the notification about {key} to: {who}. (Jira skips people who may not see the issue, "
            "and does not email the person who sent it.)"
        )
