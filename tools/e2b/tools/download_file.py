from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from e2b_code_interpreter import Sandbox


class DownloadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        sandbox_id = tool_parameters.get("sandbox_id", "")
        file_path = tool_parameters.get("file_path", "")

        if not sandbox_id:
            raise ValueError("Sandbox ID is required")

        if not file_path:
            raise ValueError("File path is required")

        args = {
            "api_key": self.runtime.credentials["api_key"],
            "sandbox_id": sandbox_id,
            "timeout": tool_parameters.get("timeout", 120),
        }

        sandbox = Sandbox(**args)

        file = sandbox.files.read(file_path)

        yield self.create_json_message({
            "file_text": file,
        })
