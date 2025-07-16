from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.comfyui_client import ComfyUiClient, FileType
from tools.comfyui_workflow import ComfyUiWorkflow
from dify_plugin import Tool


def clean_json_string(s):
    for char in ["\n", "\r", "\t", "\x08", "\x0c"]:
        s = s.replace(char, "")
    for char_id in range(0x007F, 0x00A1):
        s = s.replace(chr(char_id), "")
    return s


class ComfyUIWorkflowTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        self.comfyui = ComfyUiClient(self.runtime.credentials["base_url"])
        images = tool_parameters.get("images") or []
        workflow = ComfyUiWorkflow(
            clean_json_string(tool_parameters.get("workflow_json"))
        )
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type)
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
                f"Failed to generate image: {str(e)}. Please check if the workflow JSON works on ComfyUI."
            )

        for img in output_images:
            yield self.create_blob_message(
                blob=img["data"],
                meta={
                    "filename": img["filename"],
                    "mime_type": img["mime_type"],
                },
            )
