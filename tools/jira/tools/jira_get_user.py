from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, jira_request, resolve_context, user_dict
from tools.outputs import with_outputs


class JiraGetUserTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """A user by account ID (Cloud) or username (Server); without one, the signed-in account itself."""
        account_id = str(tool_parameters.get("account_id") or "").strip()
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            if account_id:
                params = {"accountId" if ctx.cloud else "username": account_id, "expand": "groups"}
                user = jira_request(ctx, "GET", ctx.api("user"), params=params).json()
            else:
                user = jira_request(ctx, "GET", ctx.api("myself"), params={"expand": "groups"}).json()
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = user_dict(user)
        result["groups"] = [g.get("name", "") for g in (user.get("groups") or {}).get("items") or []]
        result["time_zone"] = user.get("timeZone", "")
        self._out.update(
            account_id=result["account_id"], display_name=result["display_name"], email=result["email"], success=True
        )
        yield self.create_json_message(result)
        yield self.create_text_message(
            f"{result['display_name']} (account ID {result['account_id']}"
            + (f", {result['email']}" if result["email"] else "")
            + ")"
        )
