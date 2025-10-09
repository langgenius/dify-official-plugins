import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.httpclient import APIRequestTool
from utils.json2table import json2table


class GetEntryTool(Tool):
    """
    get the entry list of a specific application
    """

    def getEntryList(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            access_token = self.runtime.credentials["jiandaoyun_api_key"]
            base_url = self.runtime.credentials["base_url"] or "https://api.jiandaoyun.com/"
        except KeyError:
            raise Exception("jiandaoyun api-key is missing or invalid.")
        httpClient = APIRequestTool(base_url=base_url, token=access_token)
        return httpClient.create("/v5/app/entry/list", data=data)

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        app_id = tool_parameters.get("app_id")
        if not app_id:
            raise ValueError("app_id is required to invoke this tool")
        limit = tool_parameters.get("limit", 100)
        offset = tool_parameters.get("offset", 0)
        output_type = tool_parameters.get("output_type", "json")
        response = self.getEntryList(
            {"app_id": app_id, "limit": limit, "offset": offset},
        )
        if response.get("status") != "success":
            raise ValueError(
                f"Fail to fetch the entry list: {response.get('message', 'Unknown error')}"
            )
        response = response.get("data")
        json_data = {
            "status": "success",
            "data": response,
            "message": "Successfully fetched entry list",
        }
        try:
            dumped_data = json.dumps(json_data)
        except json.JSONDecodeError:
            raise ValueError("the response is not a valid JSON format")
        if output_type == "json":
            yield self.create_text_message(dumped_data)
        elif output_type == "table":
            output_data = json2table(response["forms"])
            yield self.create_text_message(output_data)
