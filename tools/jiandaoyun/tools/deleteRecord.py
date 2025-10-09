import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.httpclient import APIRequestTool


class DataupdateTool(Tool):
    """
    delete a record in jiandaoyun
    """

    def updateData(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            access_token = self.runtime.credentials["jiandaoyun_api_key"]
            base_url = self.runtime.credentials["base_url"] or "https://api.jiandaoyun.com/"
        except KeyError:
            raise Exception("jiandaoyun api-key is missing or invalid.")
        httpClient = APIRequestTool(base_url=base_url, token=access_token)
        return httpClient.create("v5/app/entry/data/delete", data=data)["data"]

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        app_id = tool_parameters.get("app_id", "")
        if not app_id:
            raise ValueError("app_id is required to invoke this tool")
        entry_id = tool_parameters.get("entry_id", None)
        if not entry_id:
            raise ValueError("entry_id is required to invoke this tool")
        data_id = tool_parameters.get("data_id", None)
        if not data_id:
            raise ValueError("data_id is required to invoke this tool")
        data_update = self.updateData(
            {"app_id": app_id, "entry_id": entry_id, "data_id": data_id},
        )
        try:
            data = json.dumps(data_update)
        except json.JSONDecodeError:
            raise ValueError(
                "JSON decoding error: the response is not a valid JSON format"
            )
        json_data = {
            "status": "success",
            "data": data,
            "message": "Data deleted successfully",
        }

        yield self.create_text_message(json.dumps(json_data))
