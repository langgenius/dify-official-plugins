import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.httpclient import APIRequestTool
from utils.json2table import json2table


class DatagetlistTool(Tool):
    """
    get records list from jiandaoyun
    """

    def getDataList(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            access_token = self.runtime.credentials["jiandaoyun_api_key"]
            base_url = self.runtime.credentials["base_url"] or "https://api.jiandaoyun.com/"
        except KeyError:
            raise Exception("apikey is missing or invalid.")
        httpClient = APIRequestTool(base_url=base_url, token=access_token)
        return httpClient.create("v5/app/entry/data/list", data=data)["data"]

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        app_id = tool_parameters.get("app_id", "")
        if not app_id:
            raise ValueError("app_id is required to invoke this tool")
        entry_id = tool_parameters.get("entry_id", "")
        if not entry_id:
            raise ValueError("entry_id is required to invoke this tool")
        output_type = tool_parameters.get("output_type", "json")
        data = self.getDataList(
            {
                "app_id": app_id,
                "entry_id": entry_id,
                "data_id": tool_parameters.get("data_id", None),
                "fields": tool_parameters.get("fields", None),
                "filter": tool_parameters.get("filter", "{}"),
                "limit": tool_parameters.get("limit", 10),
            },
        )
        json_data = {
            "status": "success",
            "data": data,
            "message": "Successfully fetched data list",
        }
        try:
            json_str = json.dumps(json_data)
        except json.JSONDecodeError:
            raise ValueError(
                "JSON decoding error: the response is not a valid JSON format"
            )
        if output_type == "table":
            output_data = json2table(data["data"])
            yield self.create_text_message(output_data)
        elif output_type == "json":
            yield self.create_text_message(json_str)
