import json
from typing import Any, Generator

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class OpenweatherTool(Tool):
    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        city = tool_parameters.get("city", "")
        if not city:
            yield self.create_text_message("Please tell me your city")
            return
        if "api_key" not in self.runtime.credentials or not self.runtime.credentials.get("api_key"):
            yield self.create_text_message("OpenWeather API key is required.")
            return
        units = tool_parameters.get("units", "metric")
        lang = tool_parameters.get("lang", "zh_cn")
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": city, "appid": self.runtime.credentials.get("api_key"), "units": units, "lang": lang}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                yield self.create_text_message(
                    self.session.model.summary.invoke(text=json.dumps(data, ensure_ascii=False), instruction="")
                )
            else:
                error_message = {"error": f"failed:{response.status_code}", "data": response.text}
                yield json.dumps(error_message)
        except Exception as e:
            yield self.create_text_message("Openweather API Key is invalid. {}".format(e))
