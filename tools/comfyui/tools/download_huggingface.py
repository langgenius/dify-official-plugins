from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient
from tools.model_manager import ModelManager


class DownloadHuggingFace(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")

        self.comfyui = ComfyUiClient(
            base_url, self.runtime.credentials.get("comfyui_api_key")
        )
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=None,
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )

        repo_id = tool_parameters.get("repo_id", "")
        filepath = tool_parameters.get("filepath", "")
        save_dir = tool_parameters.get("save_dir", "")

        filename = self.model_manager.download_hugging_face(
            repo_id, filepath, save_dir)
        yield self.create_variable_message("filename", filename)
