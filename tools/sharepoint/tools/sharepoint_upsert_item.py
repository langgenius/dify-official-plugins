from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import (
    GraphAuthError,
    context_for,
    get_all,
    graph_request,
    item_dict,
    odata_literal,
    parse_fields,
    require,
    resolve_site,
)
from tools.outputs import with_outputs

NON_INDEXED = {"Prefer": "HonorNonIndexedQueriesWarningMayFailRandomly"}


class UpsertItemTool(Tool):
    """
    Update the item whose match columns equal the given values, or create it (n8n: Item >
    Create or Update). More than one matching item is an error, as in n8n.
    """

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, match_text = require(tool_parameters, "list", "match_columns")
            fields = parse_fields(tool_parameters.get("fields"))
            match_columns = [c.strip() for c in match_text.split(",") if c.strip()]
            missing = [c for c in match_columns if c not in fields]
            if missing:
                raise GraphAuthError(f"fields must include a value for each match column: {', '.join(missing)}.")
            ctx = context_for(self, tool_parameters)
            site_id = resolve_site(ctx, tool_parameters.get("site"))["site_id"]
            query = " and ".join(f"fields/{c} eq {odata_literal(fields[c])}" for c in match_columns)
            matches = get_all(ctx, ctx.items(site_id, list_id), {"$expand": "fields", "$filter": query, "$top": 2}, 2, headers=NON_INDEXED)
            if len(matches) > 1:
                raise GraphAuthError(f"More than one item matches {query}; use columns that identify one item.")
            if matches:
                item_id = str(matches[0]["id"])
                graph_request(ctx, "PATCH", f"{ctx.item(site_id, list_id, item_id)}/fields", json_body=fields)
                action = "updated"
            else:
                item_id = item_dict(graph_request(ctx, "POST", ctx.items(site_id, list_id), json_body={"fields": fields}).json())["item_id"]
                action = "created"
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to create or update the item: {e}")
            return
        self._out.update(item_id=item_id, action=action, success=True)
        yield self.create_text_message(f"{action.capitalize()} item {item_id} (matched on {', '.join(match_columns)}).")
        yield self.create_json_message({"item_id": item_id, "action": action})
