from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, jira_request, require, resolve_context, segment
from tools.jira_fields import issue_fields
from tools.outputs import with_outputs


class JiraUpdateIssueTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Change an issue's fields; only the parameters that are given are changed."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (key,) = require(tool_parameters, "issue_key")
            fields = issue_fields(ctx, tool_parameters)
            if not fields:
                raise JiraAuthError("Nothing to update: give at least one field to change.")
            params = {"notifyUsers": "false"} if tool_parameters.get("notify_users") is False else None
            jira_request(ctx, "PUT", ctx.api(f"issue/{segment(key)}"), json_body={"fields": fields}, params=params)
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(issue_key=key, updated_fields=sorted(fields), url=ctx.browse(key), success=True)
        yield self.create_json_message({"issue_key": key, "updated_fields": sorted(fields)})
        yield self.create_text_message(f"Updated {key}: {', '.join(sorted(fields))}.")
