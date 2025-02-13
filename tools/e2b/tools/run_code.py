from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from e2b_code_interpreter import Sandbox


class RunCodeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        sandbox_id = tool_parameters.get("sandbox_id", "")

        args = {
            "api_key": self.runtime.credentials["api_key"],
            "timeout": tool_parameters.get("timeout", 120),
        }

        if sandbox_id:
            args["sandbox_id"] = sandbox_id

        language = tool_parameters.get("language", "python")
        language = language.lower()

        if language not in ["python", "javascript"]:
            raise ValueError(f"Invalid language: {language}")

        sandbox = Sandbox(**args)

        execution = sandbox.run_code(tool_parameters["code"], language)

        yield self.create_json_message({
            "results": execution.results,
            "logs": execution.logs,
            "error": execution.error,
            "sandbox_id": sandbox.sandbox_id,
        })
