from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, confluence_request, require, resolve_context, segment
from tools.outputs import with_outputs


class ConfluenceAddLabelsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Add labels to a page (labels it already has are kept)."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            page_id, raw = require(tool_parameters, "page_id", "labels")
            # Confluence labels are lowercase and cannot contain spaces.
            names = [n.strip().lower().replace(" ", "-") for n in raw.split(",") if n.strip()]
            if not names:
                raise ConfluenceAuthError("labels is required.")
            body = [{"prefix": "global", "name": name} for name in names]
            result = confluence_request(ctx, "POST", ctx.v1(f"content/{segment(page_id)}/label"), json_body=body).json()
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        labels = [label.get("name", "") for label in (result.get("results") or [])] or names
        self._out.update(labels=labels, success=True)
        yield self.create_json_message({"page_id": page_id, "labels": labels})
        yield self.create_text_message(f"The page's labels are now: {', '.join(labels)}.")
