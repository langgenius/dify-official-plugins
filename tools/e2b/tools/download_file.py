from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

try:
    from e2b_sandbox import get_sandbox
except ModuleNotFoundError:
    from tools.e2b.e2b_sandbox import get_sandbox


class DownloadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        sandbox_id = tool_parameters.get("sandbox_id", "")
        file_path = tool_parameters.get("file_path", "")

        if not sandbox_id:
            raise ValueError("Sandbox ID is required")

        if not file_path:
            raise ValueError("File path is required")

        sandbox = get_sandbox(
            api_key=self.runtime.credentials["api_key"],
            domain=self.runtime.credentials.get("domain"),
            timeout=tool_parameters.get("timeout", 120),
            sandbox_id=sandbox_id,
        )

        file = sandbox.files.read(file_path)

        yield self.create_json_message({
            "file_text": file,
        })
