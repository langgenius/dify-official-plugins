from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.confluence_client import ConfluenceAuthError, confluence_request, resolve_context, segment, to_storage


class CreatePageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Create a page in selected space in Confluence.
        """
        try:
            ctx = resolve_context(self.runtime.credentials, self)
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        if getattr(self, "_signed_in_as", None):
            yield self.create_text_message(
                f"(Signed in to Atlassian as {self._signed_in_as}. If this is not the user's account, "
                "they can ask to sign out and sign in again.)"
            )
        space_key = str(tool_parameters.get("space_key") or "").strip()
        title = tool_parameters.get("title")
        # "storage" (the default, as before) or "markdown".
        body = to_storage(tool_parameters.get("body") or "", tool_parameters.get("body_format") or "storage")
        parent_id = str(tool_parameters.get("parent_id") or "").strip()

        try:
            if ctx.cloud:
                spaces = confluence_request(ctx, "GET", ctx.v2("spaces"), params={"keys": space_key}).json()
                space = next(iter(spaces.get("results") or []), None)
            else:
                space = confluence_request(ctx, "GET", ctx.v1(f"space/{segment(space_key)}")).json()
        except ConfluenceAuthError:
            space = None
        if not space:
            yield self.create_text_message("Space not found")
            return

        try:
            if ctx.cloud:
                # The v2 API takes the body as {"representation", "value"}; the {"storage": {...}} shape that
                # atlassian-python-api sends makes Confluence Cloud answer 500.
                payload: dict[str, Any] = {"spaceId": str(space["id"]), "status": "current", "title": title,
                                           "body": {"representation": "storage", "value": body}}
                if parent_id:
                    payload["parentId"] = parent_id
                page = confluence_request(ctx, "POST", ctx.v2("pages"), json_body=payload).json()
            else:
                payload = {"type": "page", "title": title, "space": {"key": space_key},
                           "body": {"storage": {"value": body, "representation": "storage"}}}
                if parent_id:
                    payload["ancestors"] = [{"id": parent_id}]
                page = confluence_request(ctx, "POST", ctx.v1("content"), json_body=payload).json()
            yield self.create_text_message("Page created successfully")
            if isinstance(page, dict) and page.get("id"):
                yield self.create_json_message({"id": str(page["id"]), "title": page.get("title", title)})

        except ConfluenceAuthError as e:
            yield self.create_text_message(f"Failed to create page: {str(e)}")
            return
