from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, clamp, jira_request, require, resolve_context, user_dict
from tools.outputs import with_outputs


class JiraSearchUsersTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Find people by name or email, to get the account ID that assignee and notify need."""
        limit = clamp(tool_parameters.get("limit"), 20, 100)
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (query,) = require(tool_parameters, "query")
            # Cloud searches with "query"; Server / Data Center with "username" (which also matches names and emails).
            params = {"query" if ctx.cloud else "username": query, "maxResults": limit}
            users = jira_request(ctx, "GET", ctx.api("user/search"), params=params).json()
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        # Cloud also returns app and customer accounts; people are "atlassian" accounts.
        result = [user_dict(u) for u in users or [] if u.get("accountType", "atlassian") == "atlassian"][:limit]
        self._out.update(users=result, count=len(result), success=True)
        yield self.create_json_message({"users": result})
        yield self.create_text_message(
            "Found: " + "; ".join(f"{u['display_name']} (account ID {u['account_id']})" for u in result)
            if result
            else f"No users match '{query}'."
        )
