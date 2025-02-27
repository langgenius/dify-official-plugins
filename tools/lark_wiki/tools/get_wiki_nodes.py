from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class GetWikiNodesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        space_id = tool_parameters.get("space_id")
        parent_node_token = tool_parameters.get("parent_node_token")
        page_token = tool_parameters.get("page_token")
        page_size = tool_parameters.get("page_size")
        res = client.get_wiki_nodes(space_id, parent_node_token, page_token, page_size)
        yield self.create_json_message(res)
