from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.resemble_api import (
    ResembleClient, ResembleError, build_detect_body, extract_uuid,
    sanitize_output, summarize_detection, to_int,
)


class DetectTool(Tool):
    """Deepfake detection on audio, image, or video. Every analysis option is a
    toggle the user sets in the node — intelligence, source tracing, visualize,
    reverse search, OOD, zero-retention, region/frame controls, and async callback."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        creds = self.runtime.credentials
        client = ResembleClient(
            api_key=creds.get("resemble_api_key"),
            base_url=creds.get("base_url"),
        )

        if not (tool_parameters.get("url") or "").strip():
            raise ValueError("`url` is required — a public HTTPS link to the media to analyze.")

        body = build_detect_body(tool_parameters)
        callback_url = body.get("callback_url")

        try:
            submitted = client.request("POST", "/detect", json_body=body)
            uuid = extract_uuid(submitted)

            # Async mode: hand back the job id, let Resemble POST to the callback.
            if callback_url and uuid:
                yield self.create_json_message(
                    {"uuid": uuid, "status": "submitted", "callback_url": callback_url}
                )
                yield self.create_text_message(
                    f"Detection submitted (uuid={uuid}). Resemble will POST the result "
                    f"to your callback URL when complete."
                )
                return

            # Some deployments may return a finished result synchronously.
            if not uuid:
                yield self.create_json_message(sanitize_output(submitted))
                yield self.create_text_message(summarize_detection(submitted))
                return

            max_wait = to_int(tool_parameters.get("max_wait_seconds"), 120)
            result = client.poll(f"/detect/{uuid}", max_wait_seconds=max_wait)
        except ResembleError as exc:
            raise ValueError(str(exc)) from exc

        yield self.create_json_message(sanitize_output(result))
        yield self.create_text_message(summarize_detection(result))
