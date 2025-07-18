import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from pymstodo import ToDoConnection
from pymstodo.client import Token


class GetListsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        token: Token = Token(**json.loads(self.runtime.credentials["token"]))
        if not token:
            raise ValueError("Token is required to invoke this tool.")

        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        lists = [
            {
                "list_id": task_list.list_id,
                "display_name": task_list.displayName,
                "is_owner": task_list.isOwner,
                "is_shared": task_list.isShared,
                "link": task_list.link,
            }
            for task_list in todo_client.get_lists()
        ]

        yield self.create_json_message(
            {
                "data": lists,
            }
        )

        yield self.create_text_message(str(lists))
