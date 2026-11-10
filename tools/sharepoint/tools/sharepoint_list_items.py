from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, get_all, item_dict, require, resolve_site
from tools.outputs import with_outputs

# Filtering on a column that is not indexed is refused unless the request says it accepts that it may fail on big lists.
NON_INDEXED = {"Prefer": "HonorNonIndexedQueriesWarningMayFailRandomly"}


class ListItemsTool(Tool):
    """Items of a list, optionally filtered."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        filter_text = str(tool_parameters.get("filter") or "").strip()
        try:
            (list_id,) = require(tool_parameters, "list")
            limit = max(1, min(int(tool_parameters.get("limit") or 100), 5000))
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            params: dict[str, Any] = {"$expand": "fields", "$top": min(limit, 500)}
            if filter_text:
                params["$filter"] = filter_text
            items = [item_dict(i) for i in get_all(ctx, ctx.items(site["site_id"], list_id), params, limit, headers=NON_INDEXED if filter_text else None)]
        except (GraphAuthError, ValueError) as e:
            hint = ""
            if filter_text and "400" in str(e):
                hint = " Filters use column names with a fields/ prefix, e.g. fields/Status eq 'Done'."
            yield self.create_text_message(f"Failed to get the list items: {e}{hint}")
            return
        self._out.update(items=items, count=len(items), success=True)
        yield self.create_text_message(f"{len(items)} item(s)" + (f" matching {filter_text}" if filter_text else "") + ".")
        yield self.create_json_message({"items": items, "count": len(items)})
