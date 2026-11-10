from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, clamp, jira_request, require, resolve_context, segment
from tools.outputs import with_outputs


def history_dict(history: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(history.get("id", "")),
        "author": (history.get("author") or {}).get("displayName", ""),
        "created": history.get("created", ""),
        "changes": [
            {"field": item.get("field", ""), "from": item.get("fromString") or "", "to": item.get("toString") or ""}
            for item in history.get("items") or []
        ],
    }


class JiraGetChangelogTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """An issue's change history: who changed which field from what to what, newest last."""
        limit = clamp(tool_parameters.get("limit"), 100, 1000)
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (key,) = require(tool_parameters, "issue_key")
            histories: list[dict[str, Any]] = []
            if ctx.cloud:
                while len(histories) < limit:
                    page = jira_request(
                        ctx, "GET", ctx.api(f"issue/{segment(key)}/changelog"),
                        params={"startAt": len(histories), "maxResults": min(100, limit - len(histories))},
                    ).json()
                    batch = page.get("values") or []
                    histories.extend(batch)
                    if not batch or page.get("isLast", True):
                        break
            else:
                issue = jira_request(
                    ctx, "GET", ctx.api(f"issue/{segment(key)}"), params={"expand": "changelog", "fields": "summary"}
                ).json()
                histories = (issue.get("changelog") or {}).get("histories") or []
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        changes = [history_dict(h) for h in histories[:limit]]
        self._out.update(histories=changes, count=len(changes), success=True)
        yield self.create_json_message({"issue_key": key, "histories": changes})
        yield self.create_text_message(f"{key} has {len(changes)} change(s) in its history.")
