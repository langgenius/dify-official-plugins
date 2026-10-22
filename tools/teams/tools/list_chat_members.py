from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, segment
from tools.outputs import with_outputs


class ListChatMembersTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (chat_id,) = require(tool_parameters, "chat_id")
            data = graph.request("GET", f"/chats/{segment(chat_id)}/members").json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        members = [
            {
                "id": m.get("id"),
                "userId": m.get("userId"),
                "displayName": m.get("displayName"),
                "email": m.get("email"),
                "roles": m.get("roles"),
            }
            for m in data.get("value", [])
        ]
        yield self.create_text_message(f"Found {len(members)} member(s) in the chat.")
        self._out.update(members=[{"name": m["displayName"] or "", "email": m["email"] or "", "user_id": m["userId"] or "", "roles": list(m["roles"] or [])} for m in members], count=len(members), success=True)
        yield self.create_json_message({"members": members})
