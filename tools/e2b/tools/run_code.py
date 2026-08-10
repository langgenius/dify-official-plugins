from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

try:
    from e2b_sandbox import get_sandbox
except ModuleNotFoundError:
    from tools.e2b.e2b_sandbox import get_sandbox


class RunCodeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        sandbox_id = tool_parameters.get("sandbox_id", "")

        timeout = tool_parameters.get("timeout", 120)

        language = tool_parameters.get("language", "python")
        language = language.lower()

        if language not in ["python", "javascript"]:
            raise ValueError(f"Invalid language: {language}")

        sandbox = get_sandbox(
            api_key=self.runtime.credentials["api_key"],
            domain=self.runtime.credentials.get("domain"),
            timeout=timeout,
            sandbox_id=sandbox_id or None,
        )

        execution = sandbox.run_code(tool_parameters["code"], language)

        yield self.create_json_message({
            "results": execution.results,
            "logs": execution.logs,
            "error": execution.error,
            "sandbox_id": sandbox.sandbox_id,
        })
