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
        base_url = "http://api.tianditu.gov.cn/staticimage"
        keyword = tool_parameters.get("keyword", "")
        if not keyword:
            yield self.create_text_message("Invalid parameter keyword")
            return

        tk = self.runtime.credentials.get("tianditu_api_key")
        if not tk:
            yield self.create_text_message("Tianditu API key is required.")
            return

        try:
            geo_response = requests.get(
                geocoder_base_url
                + "?ds="
                + json.dumps({"keyWord": keyword}, ensure_ascii=False)
                + "&tk="
                + tk,
                timeout=10,
            )
            geo_response.raise_for_status()
            keyword_coords = geo_response.json()
            coords = (
                str(keyword_coords["location"]["lon"])
                + ","
                + str(keyword_coords["location"]["lat"])
            )
            img_response = requests.get(
                base_url
                + "?center="
                + coords
                + "&markers="
                + coords
                + "&width=400&height=300&zoom=14&tk="
                + tk,
                timeout=10,
            )
            img_response.raise_for_status()
            result = img_response.content
        except requests.exceptions.RequestException:
            yield self.create_text_message(_NETWORK_ERROR)
            return
        yield self.create_blob_message(
            blob=result,
            meta={"mime_type": "image/png"},
        )
