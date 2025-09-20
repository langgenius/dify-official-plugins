import json
from collections.abc import Generator
from typing import Any, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.httpclient import APIRequestTool
from utils.json2table import json2table


class AppTool(Tool):
    """
    get app list in jiandaoyun
    """

    def get_app_list(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            access_token = self.runtime.credentials["jiandaoyun_api_key"]
            base_url = self.runtime.credentials["base_url"] or "https://api.jiandaoyun.com/"
        except KeyError:
            raise Exception("jiandaoyun api-key is missing or invalid.")
        httpClient = APIRequestTool(base_url=base_url, token=access_token)
        return httpClient.create("v5/app/list", data=data)

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        limit = tool_parameters.get("limit", 10)
        offset = tool_parameters.get("offset", 0)
        output_type = tool_parameters.get("output_type", "json")

        response = self.get_app_list(
            {"limit": limit, "skip": offset},
        )
        if response.get("status") != "success":
            raise ValueError(
                f"Fail to fetch the app list: {response.get('message', 'Unknown error')}"
            )
        response = response.get("data")
        if output_type == "json":
            concat_data = json.dumps(response, ensure_ascii=False, indent=2)
            yield self.create_text_message(concat_data)
        elif output_type == "table":
            output_data = json2table(response["apps"])
            yield self.create_text_message(output_data)
        else:
            raise ValueError(
                f"""Unsupported output_type: {output_type}
                (supported types: "json", "table")"""
            )
