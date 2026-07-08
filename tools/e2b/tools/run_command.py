from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

try:
    from e2b_sandbox import get_sandbox
except ModuleNotFoundError:
    from tools.e2b.e2b_sandbox import get_sandbox


class RunCommandTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        sandbox_id = tool_parameters.get("sandbox_id", "")

        sandbox = get_sandbox(
            api_key=self.runtime.credentials["api_key"],
            domain=self.runtime.credentials.get("domain"),
            timeout=tool_parameters.get("timeout", 120),
            sandbox_id=sandbox_id or None,
        )

        execution = sandbox.commands.run(tool_parameters["command"])

        yield self.create_json_message({
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "exit_code": execution.exit_code,
            "error": execution.error,
            "sandbox_id": sandbox.sandbox_id,
        })
