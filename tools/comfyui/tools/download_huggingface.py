import json
import os
import uuid
from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage

from dify_plugin import Tool
import requests
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
            base_url, self.runtime.credentials.get("comfyui_api_key")
        )

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "download.json")) as file:
            workflow_json = json.loads(file.read())

        repo_id = tool_parameters.get("repo_id", "")
        filename = tool_parameters.get("filename", "")
        save_dir = tool_parameters.get("save_dir", "")

        workflow_json["1"]["inputs"][
            "url"
        ] = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
        workflow_json["1"]["inputs"]["filename"] = filename.split("/")[-1]
        workflow_json["1"]["inputs"]["token"] = hf_api_key
        workflow_json["1"]["inputs"]["save_to"] = save_dir

        response = requests.head(
            workflow_json["1"]["inputs"]["url"],
            headers={"Authorization": f"Bearer {hf_api_key}"},
        )
        if response.status_code >= 400:
            raise ToolProviderCredentialValidationError(
                "Download failed. Please check URL and api_token."
            )
        workflow_json["1"]["inputs"][
            "url"
        ] = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
        workflow_json["1"]["inputs"]["filename"] = filename.split("/")[-1]
        workflow_json["1"]["inputs"]["token"] = hf_api_key
        workflow_json["1"]["inputs"]["save_to"] = save_dir

        response = requests.head(
            workflow_json["1"]["inputs"]["url"],
            headers={"Authorization": f"Bearer {hf_api_key}"},
        )
        if response.status_code >= 400:
            raise ToolProviderCredentialValidationError(
                "Download failed. Please check URL and api_token."
            )

        try:
            output_images = self.comfyui.generate(workflow_json)
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to download: {str(e)}. Please make sure https://github.com/ServiceStack/comfy-asset-downloader works on ComfyUI"
            )
        yield self.create_variable_message("filename", filename)
