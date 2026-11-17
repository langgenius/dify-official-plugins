from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, require, resolve_context, to_storage
from tools.confluence_pages import get_page, put_page
from tools.outputs import with_outputs

MODES = ("replace", "append", "prepend")


class ConfluenceUpdatePageTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Change a page's title and/or content: replace it, or add to its end or start."""
        mode = str(tool_parameters.get("mode") or "replace").lower()
        try:
            if mode not in MODES:
                raise ConfluenceAuthError(f"mode must be one of: {', '.join(MODES)}.")
            ctx = resolve_context(self.runtime.credentials, self)
            (page_id,) = require(tool_parameters, "page_id")
            new_title = str(tool_parameters.get("title") or "").strip()
            content = tool_parameters.get("body")
            if not new_title and not content:
                raise ConfluenceAuthError("Nothing to update: give a new title and/or body.")
            page = get_page(ctx, page_id)
            storage = page["body_storage"]
            if content:
                added = to_storage(str(content), tool_parameters.get("body_format"))
                storage = {"replace": added, "append": storage + added, "prepend": added + storage}[mode]
            saved = put_page(ctx, page, new_title or page["title"], storage, str(tool_parameters.get("version_message") or ""))
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(page_id=saved["id"] or page_id, title=saved["title"], version=saved["version"],
                         url=saved["url"] or page["url"], success=True)
        yield self.create_json_message(saved)
        action = {"replace": "Updated", "append": "Appended to", "prepend": "Prepended to"}[mode] if content else "Renamed"
        yield self.create_text_message(f"{action} '{saved['title']}' (now version {saved['version']}).")
