from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.resemble_api import (
    ResembleClient, ResembleError, extract_uuid, sanitize_output, to_int, unwrap,
)


class DetectAskTool(Tool):
    """Ask a natural-language question about a COMPLETED detection
    (POST /detects/{uuid}/intelligence, then poll for the answer)."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        creds = self.runtime.credentials
        client = ResembleClient(
            api_key=creds.get("resemble_api_key"),
            base_url=creds.get("base_url"),
        )

        detect_uuid = (tool_parameters.get("detect_uuid") or "").strip()
        query = (tool_parameters.get("query") or "").strip()
        if not detect_uuid:
            raise ValueError("`detect_uuid` is required (the UUID of a completed detection).")
        if not query:
            raise ValueError("`query` is required (the question to ask about the detection).")

        try:
            submitted = client.request(
                "POST", f"/detects/{detect_uuid}/intelligence", json_body={"query": query}
            )
            question_uuid = extract_uuid(submitted)
            if not question_uuid:
                yield self.create_json_message(sanitize_output(submitted))
                yield self.create_text_message(
                    unwrap(submitted).get("answer") or "Question submitted (see JSON output)."
                )
                return

            max_wait = to_int(tool_parameters.get("max_wait_seconds"), 120)
            result = client.poll(
                f"/detects/{detect_uuid}/intelligence/{question_uuid}",
                max_wait_seconds=max_wait,
            )
        except ResembleError as exc:
            msg = str(exc)
            if "422" in msg:
                raise ValueError(
                    "The detection is not completed yet — questions can only be asked "
                    "after detection status is 'completed'."
                ) from exc
            raise ValueError(msg) from exc

        item = unwrap(result)
        answer = item.get("answer")
        yield self.create_json_message(sanitize_output(result))
        yield self.create_text_message(
            answer if answer else "Answer not ready yet — raise max_wait_seconds and retry."
        )
