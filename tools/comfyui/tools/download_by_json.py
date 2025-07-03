import json
from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


def clean_json_string(s):
    for char in ["\n", "\r", "\t", "\x08", "\x0c"]:
        s = s.replace(char, "")
    for char_id in range(0x007F, 0x00A1):
        s = s.replace(chr(char_id), "")
    return s


class DownloadByJson(Tool):
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

        input_json = json.loads(clean_json_string(
            tool_parameters.get("workflow_json")))
        models = []
        for node in input_json["nodes"]:
            if "properties" in node and "models" in node["properties"]:
                models += node["properties"]["models"]

        for model in models:
            token = None
            if "://civitai.com" in model["url"]:
                token = self.get_civit_key()
            elif "://huggingface.co" in model["url"]:
                token = self.get_hf_key()

            self.comfyui.download_model(
                model["url"], model["directory"], model["name"], token
            )

        yield self.create_variable_message("model_names", [m["name"] for m in models])
