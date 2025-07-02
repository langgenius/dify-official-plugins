from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


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
        hf_api_key = self.runtime.credentials.get("hf_api_key")
        if hf_api_key is None:
            raise ToolProviderCredentialValidationError(
                "Please input hf_api_key")

        self.comfyui = ComfyUiClient(
            base_url, self.runtime.credentials.get("comfyui_api_key")
        )

        repo_id = tool_parameters.get("repo_id", "")
        filename = tool_parameters.get("filename", "")
        save_dir = tool_parameters.get("save_dir", "")

        self.comfyui.download_model(
            f"https://huggingface.co/{repo_id}/resolve/main/{filename}",
            save_dir,
            filename.split("/")[-1],
            hf_api_key,
        )
        yield self.create_variable_message("filename", filename)
