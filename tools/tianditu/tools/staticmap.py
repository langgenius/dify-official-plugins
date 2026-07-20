import json
from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


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
            keyword_coords = requests.get(
                geocoder_base_url
                + "?ds="
                + json.dumps({"keyWord": keyword}, ensure_ascii=False)
                + "&tk="
                + tk,
                timeout=10,
            ).json()
            coords = (
                str(keyword_coords["location"]["lon"])
                + ","
                + str(keyword_coords["location"]["lat"])
            )
            result = requests.get(
                base_url
                + "?center="
                + coords
                + "&markers="
                + coords
                + "&width=400&height=300&zoom=14&tk="
                + tk,
                timeout=10,
            ).content
        except requests.exceptions.RequestException as exc:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {exc}."
            )
            return
        yield self.create_blob_message(
            blob=result,
            meta={"mime_type": "image/png"},
        )
