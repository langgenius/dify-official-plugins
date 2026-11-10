from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, list_dict, require, resolve_site
from tools.outputs import with_outputs

_TYPES = ("text", "number", "choice", "dateTime", "boolean", "personOrGroup", "lookup", "currency", "hyperlinkOrPicture",
          "calculated", "term", "geolocation", "thumbnail", "contentApprovalStatus")


class GetListTool(Tool):
    """A list and its columns, so rows can be written with the right column names."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            (list_id,) = require(tool_parameters, "list")
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            data = graph_request(ctx, "GET", ctx.list(site["site_id"], list_id), params={"$expand": "columns"}).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the list: {e}")
            return
        info = list_dict(data)
        columns = [
            {
                "name": c.get("name", ""),
                "display_name": c.get("displayName", ""),
                "type": next((t for t in _TYPES if t in c), "other"),
                "required": bool(c.get("required")),
                "read_only": bool(c.get("readOnly")),
                "choices": (c.get("choice") or {}).get("choices") or [],
            }
            for c in data.get("columns") or []
            if not c.get("hidden")
        ]
        self._out.update(info, columns=columns, success=True)
        writable = [c for c in columns if not c["read_only"]]
        yield self.create_text_message(
            f"List '{info['name']}' (id: {info['list_id']}). Columns you can write, by name: "
            + ", ".join(f"{c['name']} ({c['type']}{', required' if c['required'] else ''})" for c in writable)
        )
        yield self.create_json_message(dict(info, columns=columns))
