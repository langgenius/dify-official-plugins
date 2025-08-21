from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin import Tool
from tools.comfyui_workflow import ComfyUiWorkflow
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class Convert2API(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        workflow_json_str = tool_parameters.get("workflow_json", "")
        try:
            workflow = ComfyUiWorkflow(workflow_json_str)
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Failed to convert. {e}")
        yield self.create_text_message(workflow.json_str())
