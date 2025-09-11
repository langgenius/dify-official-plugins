import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.httpclient import APIRequestTool


class CreateRecordTool(Tool):
    """
    create a record in jiandaoyun
    """

    def create_data(self, data: dict[str, Any], base_url: str) -> dict[str, Any]:
        try:
            access_token = self.runtime.credentials["jiandaoyun_api_key"]
        except KeyError:
            raise Exception("jiandaoyun api-key is missing or invalid.")
        httpClient = APIRequestTool(base_url=base_url, token=access_token)
        return httpClient.create("v5/app/entry/data/create", data=data)["data"]

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        app_id = tool_parameters.get("app_id", "")
        if not app_id:
            raise ValueError("app_id is required to invoke this tool")
        entry_id = tool_parameters.get("entry_id", None)
        if not entry_id:
            raise ValueError("entry_id is required to invoke this tool")
        data = tool_parameters["data"]
        try:
            loaded_data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("data must be a valid JSON string")
        data = self.create_data(
            {"app_id": app_id, "entry_id": entry_id, "data": loaded_data},
            tool_parameters.get("base_url"),
        )
        json_data = {
            "status": "success",
            "data": data,
            "message": "Data created successfully",
        }
        yield self.create_text_message(str(json_data))
