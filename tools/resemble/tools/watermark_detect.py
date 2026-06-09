from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.resemble_api import (
    ResembleClient, ResembleError, sanitize_output, summarize_watermark_detect,
    watermark_error_hint,
)


class WatermarkDetectTool(Tool):
    """Check whether media contains a Resemble watermark."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        creds = self.runtime.credentials
        client = ResembleClient(
            api_key=creds.get("resemble_api_key"),
            base_url=creds.get("base_url"),
        )

        url = (tool_parameters.get("url") or "").strip()
        if not url:
            raise ValueError("`url` is required — a public HTTPS link to the media to check.")

        try:
            result = client.request(
                "POST", "/watermark/detect",
                json_body={"url": url}, extra_headers={"Prefer": "wait"},
            )
        except ResembleError as exc:
            raise ValueError(watermark_error_hint(str(exc))) from exc

        yield self.create_json_message(sanitize_output(result))
        yield self.create_text_message(summarize_watermark_detect(result))
