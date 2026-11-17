from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import MODEL, emit_images


class ImageGenerateTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        prompt = str(tool_parameters.get("prompt") or "").strip()
        if not prompt:
            yield self.create_text_message("Error: prompt is required")
            return

        yield from emit_images(
            self,
            self.runtime.credentials,
            "/v1/images/generations",
            {
                "model": MODEL,
                "prompt": prompt,
                "n": int(tool_parameters.get("n") or 1),
                "aspect_ratio": tool_parameters.get("aspect_ratio") or "1:1",
                "area": tool_parameters.get("area") or "1K",
            },
        )
