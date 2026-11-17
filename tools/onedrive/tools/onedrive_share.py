from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.outputs import with_outputs
from tools.graph_client import GraphAuthError, graph_request, resolve_graph_context, segment

_TYPES = ("view", "edit", "embed")
_SCOPES = ("anonymous", "organization")


class ShareTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Create a sharing link for a file or folder."""
        item_id = str(tool_parameters.get("item_id") or "").strip()
        link_type = str(tool_parameters.get("type") or "view").strip().lower()
        scope = str(tool_parameters.get("scope") or "organization").strip().lower()
        if not item_id:
            yield self.create_text_message("Item ID is required.")
            return
        if link_type not in _TYPES:
            yield self.create_text_message(f"Type must be one of: {', '.join(_TYPES)}.")
            return
        if scope not in _SCOPES:
            yield self.create_text_message(f"Scope must be one of: {', '.join(_SCOPES)}.")
            return

        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"), tool=self)
            permission = graph_request(
                graph,
                "POST",
                f"{graph.drive_base}/items/{segment(item_id)}/createLink",
                json={"type": link_type, "scope": scope},
            ).json()
        except GraphAuthError as e:
            hint = ""
            if "403" in str(e) or "400" in str(e):
                hint = (
                    " Your organization may not allow this kind of link (anonymous links are often turned off), "
                    "and embed links only work for personal OneDrive accounts."
                )
            yield self.create_text_message(f"Error creating the sharing link: {e}{hint}")
            return

        link = permission.get("link") or {}
        url = link.get("webUrl") or ""
        self._out.update(
            link_url=url, type=link.get("type") or link_type, scope=link.get("scope") or scope,
            permission_id=permission.get("id") or "", success=True,
        )
        who = "anyone with the link" if scope == "anonymous" else "people in your organization"
        yield self.create_text_message(f"{link_type.capitalize()} link for {who}: {url}")
        yield self.create_json_message(
            {"link_url": url, "type": link.get("type") or link_type, "scope": link.get("scope") or scope, "permission_id": permission.get("id") or ""}
        )
