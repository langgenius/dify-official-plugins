from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class ListDocumentBlockTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        document_id = tool_parameters.get("document_id")
        page_token = tool_parameters.get("page_token", "")
        user_id_type = tool_parameters.get("user_id_type", "open_id")
        page_size = tool_parameters.get("page_size", 500)
        res = client.list_document_blocks(document_id, page_token, user_id_type, page_size)
        yield self.create_json_message(res)
