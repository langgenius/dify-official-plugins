import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.httpclient import APIRequestTool
from utils.json2table import json2table


class DatagetTool(Tool):
    """
    get a record in jiandaoyun
    """

    def get_data(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            access_token = self.runtime.credentials["jiandaoyun_api_key"]
            base_url = self.runtime.credentials["base_url"] or "https://api.jiandaoyun.com/"
        except KeyError:
            raise Exception("jiandaoyun api-key is missing or invalid.")
        httpClient = APIRequestTool(base_url=base_url, token=access_token)
        return httpClient.create("v5/app/entry/data/get", data=data)

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        app_id = tool_parameters.get("app_id", "")
        if not app_id:
            raise ValueError("app_id is required to invoke this tool")
        entry_id = tool_parameters.get("entry_id", "")
        if not entry_id:
            raise ValueError("entry_id is required to invoke this tool")
        data_id = tool_parameters.get("data_id", None)
        if not data_id:
            raise ValueError("data_id is required to invoke this tool")
        output_type = tool_parameters.get("output_type", "json")
        response = self.get_data(
            {"app_id": app_id, "entry_id": entry_id, "data_id": data_id},
        )
        if response.get("status") != "success":
            raise ValueError(
                f"Fail to fetch the record: {response.get('message', 'Unknown error')}"
            )
        response_data = response["data"]
        try:
            json_data = json.dumps(response_data)
        except json.decoder.JSONDecodeError:
            raise ValueError(
                "JSON decoding error: the response is not a valid JSON format"
            )
        if output_type == "json":
            yield self.create_text_message(json_data)
        elif output_type == "table":
            table_data = json2table(response_data["data"])
            yield self.create_text_message(table_data)
