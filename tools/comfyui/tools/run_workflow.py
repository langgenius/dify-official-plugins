from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.comfyui_client import ComfyUiClient, FileType
from tools.model_manager import ModelManager
from tools.comfyui_workflow import ComfyUiWorkflow
from dify_plugin import Tool


class ComfyUIWorkflowTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        self.comfyui = ComfyUiClient(
            self.runtime.credentials["base_url"],
            api_key_comfy_org=self.runtime.credentials.get("api_key_comfy_org"),
        )
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )

        images = tool_parameters.get("images") or []
        workflow = ComfyUiWorkflow(tool_parameters.get("workflow_json", ""))
        if tool_parameters.get("enable_download", False):
            self.model_manager.download_from_json(workflow.json_original_str())

        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type
            )
            image_names.append(image_name)
        if len(image_names) > 0:
            image_ids = tool_parameters.get("image_ids")
            if image_ids is None:
                workflow.set_image_names(image_names)
            else:
                image_ids = image_ids.split(",")
                try:
                    workflow.set_image_names(image_names, image_ids)
                except Exception:
                    raise ToolProviderCredentialValidationError(
                        "the Image Node ID List not match your upload image files."
                    )

        if tool_parameters.get("randomize_seed", False):
            workflow.randomize_seed()

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}."
            )

        for img in output_images:
            yield self.create_blob_message(
                blob=img.blob,
                meta={
                    "filename": img.filename,
                    "mime_type": img.mime_type,
                },
            )
