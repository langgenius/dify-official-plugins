import json
from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

_NETWORK_ERROR = (
    "An error occurred while invoking the tool (network or upstream failure). "
    "Please retry shortly."
)


class PoiSearchTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        geocoder_base_url = "http://api.tianditu.gov.cn/geocoder"
        base_url = "http://api.tianditu.gov.cn/v2/search"
        keyword = tool_parameters.get("keyword", "")
        if not keyword:
            yield self.create_text_message("Invalid parameter keyword")
            return
        baseAddress = tool_parameters.get("baseAddress", "")
        if not baseAddress:
            yield self.create_text_message("Invalid parameter baseAddress")
            return

        tk = self.runtime.credentials.get("tianditu_api_key")
        if not tk:
            yield self.create_text_message("Tianditu API key is required.")
            return

        try:
            geo_response = requests.get(
                geocoder_base_url
                + "?ds="
                + json.dumps({"keyWord": baseAddress}, ensure_ascii=False)
                + "&tk="
                + tk,
                timeout=10,
            )
            geo_response.raise_for_status()
            base_coords = geo_response.json()
            params = {
                "keyWord": keyword,
                "queryRadius": 5000,
                "queryType": 3,
                "pointLonlat": str(base_coords["location"]["lon"])
                + ","
                + str(base_coords["location"]["lat"]),
                "start": 0,
                "count": 100,
            }
            search_response = requests.get(
                base_url
                + "?postStr="
                + json.dumps(params, ensure_ascii=False)
                + "&type=query&tk="
                + tk,
                timeout=10,
            )
            search_response.raise_for_status()
            result = search_response.json()
        except requests.exceptions.RequestException:
            yield self.create_text_message(_NETWORK_ERROR)
            return
        yield self.create_json_message(result)
