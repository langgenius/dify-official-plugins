from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class DownloadByURL(Tool):
    def get_civit_key(self) -> str:
        civitai_api_key = self.runtime.credentials.get("civitai_api_key")
        if civitai_api_key is None:
            raise ToolProviderCredentialValidationError(
                "Please input civitai_api_key")
        return civitai_api_key

    def get_hf_key(self) -> str:
        hf_api_key = self.runtime.credentials.get("hf_api_key")
        if hf_api_key is None:
            raise ToolProviderCredentialValidationError(
                "Please input hf_api_key")
        return hf_api_key

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url")
        if base_url is None:
            raise ToolProviderCredentialValidationError(
                "Please input base_url")
        self.comfyui = ComfyUiClient(base_url)

        url = tool_parameters.get("url")
        name = tool_parameters.get("name")
        if name is None or len(name) == 0:
            name = url.split("/")[-1].split("?")[0]
        token_type = tool_parameters.get("token_type")
        save_to = tool_parameters.get("save_dir")

        token = None
        if token_type == "civitai":
            token = self.get_civit_key()
        elif token_type == "hugging_face":
            token = self.get_hf_key()

        self.comfyui.download_model(url, save_to, name, token)
        yield self.create_variable_message("model_name", name)
