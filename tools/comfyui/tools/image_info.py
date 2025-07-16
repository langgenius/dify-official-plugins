import io
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin import Tool
from tools.comfyui_client import FileType
from PIL import Image


class ComfyuiImageInfo(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        files = tool_parameters.get("images") or []
        filenames = []
        mimes = []
        widths = []
        heights = []
        modes = []
        for file in files:
            filenames.append(file.filename)
            mimes.append(file.mime_type)

            width, height, mode = 0, 0, ""
            if file.type == FileType.IMAGE:
                pil_img = Image.open(io.BytesIO(file.blob))
                width = pil_img.width
                height = pil_img.height
                mode = pil_img.mode
            widths.append(width)
            heights.append(height)
            modes.append(mode)

        yield self.create_variable_message("widths", widths)
        yield self.create_variable_message("heights", heights)
        yield self.create_variable_message("modes", modes)
        yield self.create_variable_message("filenames", filenames)
        yield self.create_variable_message("mimes", mimes)
