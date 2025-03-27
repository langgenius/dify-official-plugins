from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class GetDocumentRawContentTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        document_id = tool_parameters.get("document_id")
        mode = tool_parameters.get("mode", "markdown")
        lang = tool_parameters.get("lang", "0")
        res = client.get_document_content(document_id, mode, lang)
        yield self.create_json_message(res)
