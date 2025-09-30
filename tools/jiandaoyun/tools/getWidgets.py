import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.httpclient import APIRequestTool
from utils.json2table import json2table


class WidgetTool(Tool):
    """
    get widgets of a form in jiandaoyun
    """

    def getWidget(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            access_token = self.runtime.credentials["jiandaoyun_api_key"]
            base_url = self.runtime.credentials["base_url"] or "https://api.jiandaoyun.com/"
        except KeyError:
            raise Exception("jiandaoyun api-key is missing or invalid.")
        httpClient = APIRequestTool(base_url=base_url, token=access_token)
        return httpClient.create("v5/app/entry/widget/list", data=data)["data"]

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        app_id = tool_parameters.get("app_id", "")
        if not app_id:
            raise ValueError("app_id is required to invoke this tool")
        entry_id = tool_parameters.get("entry_id", "")
        if not entry_id:
            raise ValueError("entry_id is required to invoke this tool")
        output_type = tool_parameters.get("output_type", "json")
        widget_data = self.getWidget(
            {"app_id": app_id, "entry_id": entry_id},
        )
        try:
            dumped_data = json.dumps(widget_data)
        except json.JSONDecodeError:
            raise ValueError(
                "JSON decoding error: the response is not a valid JSON format"
            )
        print(dumped_data)
        if output_type == "json":
            yield self.create_text_message(str(dumped_data))
        elif output_type == "table":
            output_data = json2table(widget_data["widgets"])
            yield self.create_text_message(output_data)
