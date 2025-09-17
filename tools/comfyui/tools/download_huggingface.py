from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.comfyui_client import ComfyUiClient
from tools.comfyui_model_manager import ModelManager


class DownloadHuggingFace(Tool):
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
            civitai_api_key=None,
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )
        filename = model_manager.download_hugging_face(
            tool_parameters.get("repo_id"), tool_parameters.get("filepath"), tool_parameters.get("save_dir")
        )
        yield self.create_variable_message("filename", filename)
