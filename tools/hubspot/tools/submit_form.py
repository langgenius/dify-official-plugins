from collections.abc import Generator
from typing import Any
import json

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

FORMS_API = "https://api.hsforms.com/submissions/v3/integration/submit"


class SubmitFormTool(Tool):
    """Submit a HubSpot form via the Forms API (no access token required)."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        portal_id = tool_parameters.get("portal_id")
        if not portal_id:
            yield self.create_text_message("'portal_id' is required.")
            return

        form_guid = tool_parameters.get("form_guid")
        if not form_guid:
            yield self.create_text_message("'form_guid' is required.")
            return

        raw_fields = tool_parameters.get("fields")
        if not raw_fields:
            yield self.create_text_message("'fields' is required.")
            return
        try:
            fields_obj = json.loads(raw_fields) if isinstance(raw_fields, str) else raw_fields
        except Exception:
            yield self.create_text_message("'fields' must be a valid JSON object.")
            return
        if not isinstance(fields_obj, dict) or not fields_obj:
            yield self.create_text_message("'fields' must be a non-empty JSON object of fieldName -> value.")
            return

        body = {"fields": [{"name": k, "value": v} for k, v in fields_obj.items()]}

        url = f"{FORMS_API}/{portal_id}/{form_guid}"
        try:
            resp = requests.post(url, json=body, timeout=30.0)
        except requests.RequestException as exc:
            yield self.create_text_message(f"HTTP error calling HubSpot Forms API: {exc}")
            return

        if not resp.ok:
            yield self.create_text_message(
                f"HubSpot Forms API error {resp.status_code}: {resp.text}"
            )
            return

        result = resp.json() if resp.text else {}
        yield self.create_text_message(f"Form submitted to portal {portal_id} (form {form_guid}).")
        yield self.create_json_message(result)
