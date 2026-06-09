from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.resemble_api import (
    ResembleClient, ResembleError, build_intelligence_body, extract_uuid,
    sanitize_output, summarize_intelligence, to_int, _status_of, TERMINAL_STATUSES,
)


class IntelligenceTool(Tool):
    """Standalone media intelligence: transcription, translation, speaker info,
    emotion, misinformation analysis, and more for audio / image / video."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        creds = self.runtime.credentials
        client = ResembleClient(
            api_key=creds.get("resemble_api_key"),
            base_url=creds.get("base_url"),
        )

        has_url = bool((tool_parameters.get("url") or "").strip())
        has_token = bool((tool_parameters.get("media_token") or "").strip())
        if not (has_url or has_token):
            raise ValueError("Provide either `url` (public HTTPS link) or `media_token`.")

        body = build_intelligence_body(tool_parameters)
        callback_url = body.get("callback_url")

        try:
            result = client.request("POST", "/intelligence", json_body=body)

            if callback_url and extract_uuid(result):
                yield self.create_json_message(
                    {"uuid": extract_uuid(result), "status": "submitted",
                     "callback_url": callback_url}
                )
                yield self.create_text_message(
                    "Intelligence submitted; result will be POSTed to your callback URL."
                )
                return

            # If still processing and we have an id, poll the resource.
            uuid = extract_uuid(result)
            status = (_status_of(result) or "").lower()
            if uuid and status and status not in TERMINAL_STATUSES:
                max_wait = to_int(tool_parameters.get("max_wait_seconds"), 120)
                try:
                    result = client.poll(f"/intelligence/{uuid}", max_wait_seconds=max_wait)
                except ResembleError:
                    # Poll path may differ by deployment — fall back to the submit payload.
                    pass
        except ResembleError as exc:
            raise ValueError(str(exc)) from exc

        yield self.create_json_message(sanitize_output(result))
        yield self.create_text_message(summarize_intelligence(result))
