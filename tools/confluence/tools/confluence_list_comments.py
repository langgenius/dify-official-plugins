from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import (
    ConfluenceAuthError,
    clamp,
    comment_dict,
    confluence_request,
    next_cursor,
    require,
    resolve_context,
    segment,
)
from tools.outputs import with_outputs


class ConfluenceListCommentsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """A page's footer comments (the ones at the bottom of the page)."""
        limit = clamp(tool_parameters.get("limit"), 50, 250)
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (page_id,) = require(tool_parameters, "page_id")
            comments: list[dict[str, Any]] = []
            if ctx.cloud:
                params: dict[str, Any] = {"body-format": "storage", "limit": min(100, limit)}
                while len(comments) < limit:
                    body = confluence_request(
                        ctx, "GET", ctx.v2(f"pages/{segment(page_id)}/footer-comments"), params=params
                    ).json()
                    comments.extend(body.get("results") or [])
                    cursor = next_cursor(body)
                    if not cursor or not body.get("results"):
                        break
                    params["cursor"] = cursor
            else:
                body = confluence_request(
                    ctx, "GET", ctx.v1(f"content/{segment(page_id)}/child/comment"),
                    params={"limit": limit, "expand": "body.storage,version"},
                ).json()
                comments = body.get("results") or []
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = [comment_dict(c) for c in comments[:limit]]
        self._out.update(comments=result, count=len(result), success=True)
        yield self.create_json_message({"page_id": page_id, "comments": result})
        yield self.create_text_message(f"The page has {len(result)} comment(s).")
