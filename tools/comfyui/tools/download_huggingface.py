import json
import os
import uuid
from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage

from dify_plugin import Tool
import requests

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
            raise ToolProviderCredentialValidationError("Please input hf_api_key")

        self.comfyui = ComfyUiClient(
            base_url,
            self.runtime.credentials.get("comfyui_api_key")
        )

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "download.json")) as file:
            draw_options = json.loads(file.read())

        repo_id = tool_parameters.get("repo_id", "")
        filename = tool_parameters.get("filename", "")
        save_dir = tool_parameters.get("save_dir", "")

        draw_options["1"]["inputs"][
            "url"
        ] = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
        draw_options["1"]["inputs"]["filename"] = filename.split("/")[-1]
        draw_options["1"]["inputs"]["token"] = hf_api_key
        draw_options["1"]["inputs"]["save_to"] = save_dir

        response = requests.head(
            draw_options["1"]["inputs"]["url"],
            headers={"Authorization": f"Bearer {hf_api_key}"},
        )
        if response.status_code >= 400:
            raise ToolProviderCredentialValidationError(
                "Download failed. Please check URL and api_token."
            )

        try:
            client_id = str(uuid.uuid4())
            self.comfyui.queue_prompt_image(client_id, prompt=draw_options)
            yield self.create_variable_message("filename", filename)
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to download: {str(e)}. Maybe install https://github.com/ServiceStack/comfy-asset-downloader on ComfyUI"
            )
