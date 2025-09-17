import os
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.comfyui_client import ComfyUiClient
from tools.comfyui_model_manager import ModelManager
from tools.comfyui_workflow import ComfyUiWorkflow


class Txt2Aud(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        cli = ComfyUiClient(
            base_url=self.runtime.credentials.get("base_url"),
            api_key=self.runtime.credentials.get("comfyui_api_key"),
            api_key_comfy_org=self.runtime.credentials.get("api_key_comfy_org"),
        )
        model_manager = ModelManager(
            cli,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "stable_audio.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        for model in workflow.get_models_to_download():
            model_manager.download_model_autotoken(model.url, model.directory, model.name)

        workflow.set_prompt("6", tool_parameters.get("prompt", ""))
        workflow.set_prompt("7", tool_parameters.get("negative_prompt", ""))
        workflow.set_k_sampler(
            None,
            int(tool_parameters.get("steps", 50)),
            tool_parameters.get("sampler", "dpmpp_3m_sde_gpu"),
            tool_parameters.get("sampler", "exponential"),
            float(tool_parameters.get("cfg", 4.98)),
            1.0,
        )

        results = cli.generate(workflow.json())
        for file in results:
            yield self.create_blob_message(
                blob=file.blob,
                meta={
                    "filename": file.filename,
                    "mime_type": file.mime_type,
                },
            )
        yield self.create_json_message(workflow.json())
