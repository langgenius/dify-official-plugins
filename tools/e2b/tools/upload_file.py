from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File

try:
    from e2b_sandbox import get_sandbox
except ModuleNotFoundError:
    from tools.e2b.e2b_sandbox import get_sandbox


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

        sandbox = get_sandbox(
            api_key=self.runtime.credentials["api_key"],
            domain=self.runtime.credentials.get("domain"),
            timeout=tool_parameters.get("timeout", 120),
            sandbox_id=sandbox_id,
        )

        sandbox.files.write(file_path, file.blob)

        yield self.create_json_message({
            "success": True,
        })
