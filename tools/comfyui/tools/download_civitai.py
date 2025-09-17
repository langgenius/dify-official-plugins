from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.comfyui_client import ComfyUiClient
from tools.comfyui_model_manager import ModelManager


class DownloadCivitAI(Tool):
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
            hf_api_key=None,
        )

        civitai_model = model_manager.search_civitai(
            tool_parameters.get("model_id"), tool_parameters.get("version_id"), tool_parameters.get("save_dir")
        )
        yield self.create_variable_message("model_name_human", civitai_model.model_name_human)
        yield self.create_variable_message("model_name", civitai_model.name)
        yield self.create_variable_message(
            "air",
            f"urn:air:{civitai_model.ecosystem}:{civitai_model.model_type}:{civitai_model.source}:{civitai_model.id}",
        )
        yield self.create_variable_message("ecosystem", civitai_model.ecosystem)
        yield self.create_variable_message("type", civitai_model.model_type)
        yield self.create_variable_message("source", civitai_model.source)

        model_manager.download_model_autotoken(civitai_model.url, civitai_model.directory, civitai_model.name)
