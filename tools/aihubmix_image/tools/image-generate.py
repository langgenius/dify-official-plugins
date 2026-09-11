from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.tool_base import AIHubMixImageMixin


class ImageGenerateTool(AIHubMixImageMixin, Tool):
    """Text-to-image, plus optional reference images for models that support them."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        yield from self._generate(
            tool_parameters,
            source_files=tool_parameters.get("reference_images"),
        )
