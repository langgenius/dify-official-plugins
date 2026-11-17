from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require, resource_dict
from tools.outputs import with_outputs

FIELDS = {"application_name": "applicationName", "display_name": "displayName", "external_id": "externalId", "web_url": "webUrl"}


class UpdateLinkedResourceTool(Tool):
    """Change a linked resource's fields."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, task_id, resource_id = require(tool_parameters, "list_id", "task_id", "linked_resource_id")
            body = {graph: str(tool_parameters[name]).strip() for name, graph in FIELDS.items() if str(tool_parameters.get(name) or "").strip()}
            if not body:
                raise GraphAuthError("Give at least one field to change (application_name, display_name, external_id, web_url).")
            if body.get("webUrl") and not body["webUrl"].lower().startswith(("https://", "http://")):
                raise GraphAuthError("web_url must start with https:// or http://.")
            ctx = context_for(self, tool_parameters)
            resource = resource_dict(graph_request(ctx, "PATCH", ctx.linked_resource(list_id, task_id, resource_id), json_body=body).json())
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to update the linked resource: {e}")
            return
        self._out.update(resource, success=True)
        yield self.create_json_message(resource)
        yield self.create_text_message(f"Updated the linked resource ({', '.join(sorted(body))}).")
