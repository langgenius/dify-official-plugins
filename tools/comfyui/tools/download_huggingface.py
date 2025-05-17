import json
import os
import uuid
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

        self.comfyui = ComfyUiClient(base_url)

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "download_huggingface.json")) as file:
            draw_options = json.loads(file.read())

        repo_id = tool_parameters.get("repo_id", "")
        filename = tool_parameters.get("filename", "")
        save_dir = tool_parameters.get("save_dir", "")

        draw_options["11"]["inputs"]["repo_id"] = repo_id
        draw_options["11"]["inputs"]["filename"] = filename
        draw_options["11"]["inputs"]["local_path"] = save_dir

        try:
            client_id = str(uuid.uuid4())
            self.comfyui.queue_prompt_image(client_id, prompt=draw_options)
            yield self.create_variable_message("filename", filename)
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}. Maybe install https://github.com/ciri/comfyui-model-downloader on ComfyUI"
            )
