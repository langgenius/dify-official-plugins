import json
from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class BarChartTool(Tool):
    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        title = tool_parameters.get("title", "")

        axis = tool_parameters.get("x_axis", "")
        if not axis:
            yield self.create_text_message("Please input x_axis")
        axis = axis.split(";")

        data = tool_parameters.get("data", "")
        if not data:
            yield self.create_text_message("Please input data")
        data = data.split(";")

        # if all data is int, convert to int
        if all(i.isdigit() for i in data):
            data = [int(i) for i in data]
        else:
            data = [float(i) for i in data]

        echarts_config = {
            "title": {
                "left": 'center',
                "text": title
            },
            "tooltip": {
                "trigger": 'axis',
                "axisPointer": {
                    "type": 'cross'
                }
            },
            "xAxis": {
                "type": 'category',
                "data": axis
            },
            "yAxis": {
                "type": 'value'
            },
            "series": [
                {
                    "data": data,
                    "type": 'bar',
                    "smooth": True
                }
            ]
        }

        output = f"```echarts\n{json.dumps(echarts_config, indent=2, ensure_ascii=False)}\n```"

        yield self.create_text_message(output)
