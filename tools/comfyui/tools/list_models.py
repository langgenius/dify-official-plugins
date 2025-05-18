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
        cli = ComfyUiClient(base_url)
        yield self.create_variable_message("checkpoints", cli.get_checkpoints())
        yield self.create_variable_message("loras", cli.get_loras())
        yield self.create_variable_message("upscale_models", cli.get_upscale_models())
