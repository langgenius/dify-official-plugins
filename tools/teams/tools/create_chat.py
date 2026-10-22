from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, split_list
from tools.outputs import with_outputs


class CreateChatTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (members_param,) = require(tool_parameters, "members")
            others = split_list(members_param)
            if not others:
                raise GraphError("members is required.")
            topic = (tool_parameters.get("topic") or "").strip()
            chat_type = "oneOnOne" if len(others) == 1 and not topic else "group"

            # The signed-in user must be one of the members.
            me = graph.request("GET", "/me", params={"$select": "id"}).json()["id"]
            members = [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    # users('...') accepts a user ID or a user principal name.
                    "user@odata.bind": f"{graph.api_base}/users('{user.replace(chr(39), '')}')",
                }
                for user in [me, *others]
            ]
            body: dict[str, Any] = {"chatType": chat_type, "members": members}
            if chat_type == "group" and topic:
                body["topic"] = topic
            data = graph.request("POST", "/chats", json=body).json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        # For a one-on-one chat that already exists, Graph returns the existing chat.
        yield self.create_text_message(f"Chat ready ({data.get('chatType')}). Chat ID: {data.get('id')}")
        self._out.update(chat_id=data.get("id") or "", chat_type=data.get("chatType") or "", web_url=data.get("webUrl") or "", success=True)
        yield self.create_json_message(data)
