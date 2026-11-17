from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools import sheets_ops
from tools.outputs import with_outputs


class GoogleSheetsUpdateRowsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        yield from sheets_ops.run(self, tool_parameters, sheets_ops.update_rows)
