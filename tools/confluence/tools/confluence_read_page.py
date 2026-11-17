from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, require, resolve_context
from tools.confluence_pages import get_page
from tools.outputs import with_outputs

# Very long pages are cut for the model; the full storage body is still in the JSON output.
MAX_TEXT = 50_000


class ConfluenceReadPageTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """A page's title, readable text, version and link."""
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (page_id,) = require(tool_parameters, "page_id")
            page = get_page(ctx, page_id)
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        text = page["body_text"]
        self._out.update(
            page_id=page["id"], title=page["title"], body_text=text, body_storage=page["body_storage"],
            version=page["version"], url=page["url"], space_id=page["space_id"], success=True,
        )
        yield self.create_json_message(page)
        cut = text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[… page truncated]"
        yield self.create_text_message(f"# {page['title']} (version {page['version']})\n{page['url']}\n\n{cut}")
