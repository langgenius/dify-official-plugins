from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, clamp, comment_dict, jira_request, require, resolve_context, segment
from tools.outputs import with_outputs


class JiraListCommentsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """An issue's comments, oldest first unless newest_first is set."""
        limit = clamp(tool_parameters.get("limit"), 50, 1000)
        order = "-created" if tool_parameters.get("newest_first") else "created"
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (key,) = require(tool_parameters, "issue_key")
            comments: list[dict[str, Any]] = []
            while len(comments) < limit:
                page = jira_request(
                    ctx, "GET", ctx.api(f"issue/{segment(key)}/comment"),
                    params={"startAt": len(comments), "maxResults": min(100, limit - len(comments)), "orderBy": order},
                ).json()
                batch = page.get("comments") or []
                comments.extend(batch)
                if not batch or len(comments) >= int(page.get("total") or 0):
                    break
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = [comment_dict(c) for c in comments[:limit]]
        self._out.update(comments=result, count=len(result), success=True)
        yield self.create_json_message({"issue_key": key, "comments": result})
        yield self.create_text_message(f"{key} has {len(result)} comment(s) listed.")
