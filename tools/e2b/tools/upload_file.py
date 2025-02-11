from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File

from e2b_code_interpreter import Sandbox


class UploadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        sandbox_id = tool_parameters.get("sandbox_id", "")
        file_path = tool_parameters.get("file_path", "")
        file = tool_parameters.get("file", "")

        if not sandbox_id:
            raise ValueError("Sandbox ID is required")

        if not file:
            raise ValueError("File is required")

        if not file_path:
            raise ValueError("File path is required")

        assert isinstance(file, File)

        args = {
            "api_key": self.runtime.credentials["api_key"],
            "sandbox_id": sandbox_id,
            "timeout": tool_parameters.get("timeout", 120),
        }

        sandbox = Sandbox(**args)

        sandbox.files.write(file_path, file.blob)

        yield self.create_json_message({
            "success": True,
        })
