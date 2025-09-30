from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)

from tools.comfyui_client import ComfyUiClient


class ComfyuiListSamplers(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        cli = ComfyUiClient(
            base_url=self.runtime.credentials.get("base_url"),
            api_key=self.runtime.credentials.get("comfyui_api_key"),
            api_key_comfy_org=self.runtime.credentials.get("api_key_comfy_org"),
        )
        yield self.create_variable_message("models", cli.get_all_models())
        yield self.create_variable_message("sampling_methods", cli.get_samplers())
        yield self.create_variable_message("schedulers", cli.get_schedulers())
