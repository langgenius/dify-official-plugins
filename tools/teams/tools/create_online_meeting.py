from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, to_graph_datetime


class CreateOnlineMeetingTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            subject, start, end = require(tool_parameters, "subject", "start_datetime", "end_datetime")
            start_utc, start_assumed = to_graph_datetime(start, "start_datetime")
            end_utc, end_assumed = to_graph_datetime(end, "end_datetime")
            if end_utc <= start_utc:
                raise GraphError("end_datetime must be after start_datetime.")
            data = graph.request(
                "POST",
                "/me/onlineMeetings",
                json={"subject": subject, "startDateTime": start_utc, "endDateTime": end_utc},
            ).json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        note = " (times without a UTC offset were taken as UTC)" if start_assumed or end_assumed else ""
        yield self.create_text_message(
            f"Online meeting created{note}. Meeting ID: {data.get('id')} Join URL: {data.get('joinWebUrl')}"
        )
        yield self.create_json_message(data)
