from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require, resource_dict
from tools.outputs import with_outputs

FIELDS = {"display_name": "displayName", "external_id": "externalId", "web_url": "webUrl"}


class CreateLinkedResourceTool(Tool):
    """Link a task to an item in another app, e.g. the email or ticket it came from."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, task_id, app = require(tool_parameters, "list_id", "task_id", "application_name")
            body = {"applicationName": app}
            body.update({graph: str(tool_parameters[name]).strip() for name, graph in FIELDS.items() if str(tool_parameters.get(name) or "").strip()})
            if body.get("webUrl") and not body["webUrl"].lower().startswith(("https://", "http://")):
                raise GraphAuthError("web_url must start with https:// or http://.")
            ctx = context_for(self, tool_parameters)
            resource = resource_dict(graph_request(ctx, "POST", ctx.linked_resources(list_id, task_id), json_body=body).json())
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to create the linked resource: {e}")
            return
        self._out.update(resource, success=True)
        yield self.create_json_message(resource)
        yield self.create_text_message(f"Linked the task to {resource['application_name']}: {resource['display_name'] or resource['web_url']}.")
