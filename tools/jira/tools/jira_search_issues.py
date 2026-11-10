from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, clamp, issue_dict, jira_request, resolve_context
from tools.outputs import with_outputs

ISSUE_FIELDS = "summary,status,issuetype,priority,assignee,reporter,project,labels,created,updated,duedate,description"
# Jira Cloud's search refuses a query without any restriction, so an empty JQL means "recently updated".
DEFAULT_JQL = "updated >= -30d ORDER BY updated DESC"


class JiraSearchIssuesTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Find issues with JQL (Jira Query Language), following pages up to the limit."""
        jql = str(tool_parameters.get("jql") or "").strip() or DEFAULT_JQL
        limit = clamp(tool_parameters.get("limit"), 50, 500)
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            raw = self._search(ctx, jql, limit)
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        issues = [issue_dict(ctx, issue) for issue in raw]
        self._out.update(issues=issues, count=len(issues), success=True)
        yield self.create_json_message({"jql": jql, "issues": issues})
        yield self.create_text_message(
            f"Found {len(issues)} issue(s)." if issues else f"No issues match: {jql}"
        )

    @staticmethod
    def _search(ctx, jql: str, limit: int) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if ctx.cloud:
            # /search was retired on Jira Cloud; /search/jql pages with nextPageToken.
            token = None
            while len(issues) < limit:
                body: dict[str, Any] = {"jql": jql, "maxResults": min(100, limit - len(issues)),
                                        "fields": ISSUE_FIELDS.split(",")}
                if token:
                    body["nextPageToken"] = token
                page = jira_request(ctx, "POST", ctx.api("search/jql"), json_body=body).json()
                issues.extend(page.get("issues") or [])
                token = page.get("nextPageToken")
                if not token or not page.get("issues"):
                    break
        else:
            while len(issues) < limit:
                params = {"jql": jql, "startAt": len(issues), "maxResults": min(100, limit - len(issues)),
                          "fields": ISSUE_FIELDS}
                page = jira_request(ctx, "GET", ctx.api("search"), params=params).json()
                batch = page.get("issues") or []
                issues.extend(batch)
                if not batch or len(issues) >= int(page.get("total") or 0):
                    break
        return issues[:limit]
