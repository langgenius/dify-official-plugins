from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import (
    ConfluenceAuthError,
    comment_dict,
    confluence_request,
    require,
    resolve_context,
    to_storage,
)
from tools.outputs import with_outputs


class ConfluenceAddCommentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Add a footer comment (Markdown) to a page."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            page_id, text = require(tool_parameters, "page_id", "comment")
            storage = to_storage(text, "markdown")
            if ctx.cloud:
                body = {"pageId": page_id, "body": {"representation": "storage", "value": storage}}
                comment = confluence_request(ctx, "POST", ctx.v2("footer-comments"), json_body=body).json()
            else:
                body = {"type": "comment", "container": {"id": page_id, "type": "page"},
                        "body": {"storage": {"value": storage, "representation": "storage"}}}
                comment = confluence_request(ctx, "POST", ctx.v1("content"), json_body=body).json()
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = comment_dict(comment)
        self._out.update(comment_id=result["id"], success=True)
        yield self.create_json_message({"page_id": page_id, "comment": result})
        yield self.create_text_message(f"Added comment {result['id']} to page {page_id}.")
