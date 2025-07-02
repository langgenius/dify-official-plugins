from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient


class ComfyuiListModels(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        cli = ComfyUiClient(
            base_url,
            self.runtime.credentials.get("comfyui_api_key")
        )
        yield self.create_variable_message("models", cli.get_model_dirs(tool_parameters.get("model_type")))
