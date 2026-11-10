from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, confluence_request, require, resolve_context, segment
from tools.outputs import with_outputs


class ConfluenceRemoveLabelTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Remove one label from a page."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            page_id, label = require(tool_parameters, "page_id", "label")
            # The query form also works for labels that contain a slash.
            confluence_request(ctx, "DELETE", ctx.v1(f"content/{segment(page_id)}/label"), params={"name": label})
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(removed=True, success=True)
        yield self.create_json_message({"page_id": page_id, "label": label, "removed": True})
        yield self.create_text_message(f"Removed the label '{label}'.")
