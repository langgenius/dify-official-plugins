import json
from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class PieChartTool(Tool):
    def _invoke(
            self, tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        title = tool_parameters.get("title", "")

        categories = tool_parameters.get("categories", "")
        if not categories:
            yield self.create_text_message("Please input categories")
        categories = categories.split(";")

        data = tool_parameters.get("data", "")
        if not data:
            yield self.create_text_message("Please input data")
        data = data.split(";")

        # if all data is int, convert to int
        if all(i.isdigit() for i in data):
            data = [int(i) for i in data]
        else:
            data = [float(i) for i in data]

        pie_data = [
            {"value": value, "name": name}
            for value, name in zip(data, categories)
        ]

        echarts_config = {
            "title": {
                "left": 'center',
                "text": title
            },
            "tooltip": {
                "trigger": 'item'
            },
            "legend": {
                "orient": 'vertical',
                "left": 'left'
            },
            "series": [
                {
                    "type": 'pie',
                    "data": pie_data
                }
            ]
        }

        output = f"```echarts\n{json.dumps(echarts_config, indent=2, ensure_ascii=False)}\n```"

        yield self.create_text_message(output)
