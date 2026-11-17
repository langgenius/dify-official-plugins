from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import (
    ConfluenceAuthError,
    clamp,
    confluence_request,
    next_cursor,
    page_dict,
    require,
    resolve_context,
    segment,
)
from tools.outputs import with_outputs


class ConfluenceListChildPagesTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """The pages directly under a page."""
        limit = clamp(tool_parameters.get("limit"), 50, 250)
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (page_id,) = require(tool_parameters, "page_id")
            children: list[dict[str, Any]] = []
            if ctx.cloud:
                params: dict[str, Any] = {"limit": min(250, limit)}
                while len(children) < limit:
                    body = confluence_request(ctx, "GET", ctx.v2(f"pages/{segment(page_id)}/children"), params=params).json()
                    children.extend(body.get("results") or [])
                    cursor = next_cursor(body)
                    if not cursor or not body.get("results"):
                        break
                    params["cursor"] = cursor
            else:
                body = confluence_request(
                    ctx, "GET", ctx.v1(f"content/{segment(page_id)}/child/page"), params={"limit": limit, "expand": "version"}
                ).json()
                children = body.get("results") or []
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        pages = [page_dict(ctx, c) for c in children[:limit]]
        self._out.update(pages=pages, count=len(pages), success=True)
        yield self.create_json_message({"page_id": page_id, "pages": pages})
        yield self.create_text_message(
            f"{len(pages)} child page(s): " + "; ".join(f"{p['title']} (id {p['id']})" for p in pages)
            if pages
            else "The page has no child pages."
        )
