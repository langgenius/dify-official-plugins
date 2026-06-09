from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.resemble_api import (
    ResembleClient, ResembleError, extract_uuid, sanitize_output, to_float,
    summarize_watermark_apply, to_int, unwrap, watermark_error_hint,
)


class WatermarkApplyTool(Tool):
    """Apply an invisible watermark to media for provenance tracking."""

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
            raise ValueError("`url` is required — a public HTTPS link to the media to watermark.")

        body: dict[str, Any] = {"url": url}
        strength = to_float(tool_parameters.get("strength"), None)
        if strength is not None:
            body["strength"] = strength
        custom_message = (tool_parameters.get("custom_message") or "").strip()
        if custom_message:
            body["custom_message"] = custom_message

        try:
            # `Prefer: wait` asks for a synchronous response when possible.
            result = client.request(
                "POST", "/watermark/apply", json_body=body, extra_headers={"Prefer": "wait"}
            )
            item = unwrap(result)
            # If async (no media yet) but we have a job id, poll the result endpoint.
            if not (item.get("watermarked_media") or item.get("url")):
                uuid = extract_uuid(result)
                if uuid:
                    max_wait = to_int(tool_parameters.get("max_wait_seconds"), 120)
                    try:
                        result = client.poll(
                            f"/watermark/apply/{uuid}/result", max_wait_seconds=max_wait
                        )
                    except ResembleError:
                        pass
        except ResembleError as exc:
            raise ValueError(watermark_error_hint(str(exc))) from exc

        yield self.create_json_message(sanitize_output(result))
        yield self.create_text_message(summarize_watermark_apply(result))
