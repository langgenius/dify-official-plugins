from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.comfyui_client import ComfyUiClient
from tools.comfyui_model_manager import ModelManager


class DownloadByURL(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        comfyui = ComfyUiClient(
            base_url=self.runtime.credentials.get("base_url"),
            api_key=self.runtime.credentials.get("comfyui_api_key"),
            api_key_comfy_org=self.runtime.credentials.get("api_key_comfy_org"),
        )
        model_manager = ModelManager(
            comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )

        url = tool_parameters.get("url")
        name = tool_parameters.get("name")
        if name is None or len(name) == 0:
            name = url.split("/")[-1].split("?")[0]
        save_to = tool_parameters.get("save_dir")
        if tool_parameters.get("use_tokens", False):
            model_manager.download_model_autotoken(url, save_to, name)
        else:
            model_manager.download_model(url, save_to, name, None)
        yield self.create_variable_message("model_name", name)
