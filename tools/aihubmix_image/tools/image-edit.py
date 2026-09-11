from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from utils.client import GatewayError
from utils.tool_base import AIHubMixImageTool


class ImageEditTool(AIHubMixImageTool):
    """Image-to-image editing: a source image (plus an optional mask) and an instruction."""

    requires_image_input = True

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        images = tool_parameters.get("images")
        if not images:
            raise GatewayError("At least one source image is required for editing")

        yield from self._generate(
            tool_parameters,
            source_files=images,
            mask=tool_parameters.get("mask"),
        )
