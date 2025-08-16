from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.model_manager import ModelManager


class DownloadByJson(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url")
        if base_url is None:
            raise ToolProviderCredentialValidationError("Please input base_url")
        self.comfyui = ComfyUiClient(base_url)
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )

        model_names = self.model_manager.download_from_json(
            tool_parameters.get("workflow_json", "")
        )

        yield self.create_variable_message("model_names", model_names)
