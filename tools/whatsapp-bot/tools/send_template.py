import json
import re
from typing import Generator, List, Optional

import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.tool import Tool


def _digits_only(s: str) -> str:
    return re.sub(r"[^0-9]", "", s or "")


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text[:500]}


def _extract_api_error(body: dict):
    if isinstance(body, dict) and "error" in body:
        err = body.get("error") or {}
        return {
            "code": err.get("code"),
            "type": err.get("type"),
            "message": err.get("message"),
            "error_subcode": err.get("error_subcode"),
        }
    return None


def _suggest_fix(api_error: dict) -> str:
    code = api_error.get("code")
    subcode = api_error.get("error_subcode")
    message = api_error.get("message") or ""

    if code == 190:
        return "Invalid or expired access token. Recreate a system user token with proper permissions."
    if code == 100:
        return "Invalid parameters. Verify 'phone_number_id', 'to', 'template.name' and 'language.code'."
    if subcode in {2018049, 131000, 131031}:
        return (
            "Recipient is outside 24h window or not opted-in. Use approved template and correct language."
        )
    if "Unsupported post request" in message:
        return "Check that the phone_number_id belongs to your app and Business Account."
    return "Check WABA setup, permissions (whatsapp_business_messaging), and recipient format (E.164 without '+')."


def list_approved_templates(access_token: str, waba_id: str) -> List[str]:
    url = f"https://graph.facebook.com/v24.0/{waba_id}/message_templates"
    headers = {"Authorization": f"Bearer {access_token}"}
    # Align with curl example: only fetch needed fields, use lowercase status
    params = {"status": "approved", "fields": "name", "limit": 100}

    names: List[str] = []
    after: Optional[str] = None
    while True:
        if after:
            params["after"] = after
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("data", []) or []:
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
        paging = data.get("paging") or {}
        cursors = paging.get("cursors") or {}
        after = cursors.get("after")
        if not after:
            break
    # de-duplicate while preserving order
    seen = set()
    result = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


class SendTemplateTool(Tool):
    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        access_token: str = (self.runtime.credentials.get("access_token") or "").strip()
        phone_number_id: str = (self.runtime.credentials.get("phone_number_id") or "").strip()
        waba_id: str = (self.runtime.credentials.get("waba_id") or "").strip()

        if not access_token or not phone_number_id or not waba_id:
            details = (
                f"have_access_token={bool(access_token)}, have_phone_number_id={bool(phone_number_id)}, "
                f"have_waba_id={bool(waba_id)}"
            )
            yield self.create_text_message(
                f"Configuration error: missing WhatsApp credentials ({details})"
            )
            return

        to_raw: str = (tool_parameters.get("to") or "").strip()
        template_name: str = (tool_parameters.get("template_name") or "").strip()
        language_code: str = (tool_parameters.get("language_code") or "en_US").strip()
        template_parameters_raw: str = (tool_parameters.get("template_parameters") or "").strip()

        if not template_name:
            yield self.create_text_message("Missing required parameter: template_name")
            return

        # Normalize recipient
        to = _digits_only(to_raw)
        if not to:
            yield self.create_text_message("Recipient phone/wa_id could not be normalized to digits.")
            return

        # Build components from template_parameters
        components = []
        if template_parameters_raw:
            parsed_components = None
            try:
                # Accept JSON array of components
                parsed_components = json.loads(template_parameters_raw)
            except Exception:
                # Fallback: comma-separated plain text parameters -> map to body placeholders
                values = [v.strip() for v in template_parameters_raw.split(",") if v.strip()]
                if values:
                    parsed_components = [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": v} for v in values],
                        }
                    ]
            if isinstance(parsed_components, list):
                components = parsed_components

        url = f"https://graph.facebook.com/v24.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            body = _safe_json(resp)
            ok = 200 <= resp.status_code < 300
            if ok:
                yield self.create_text_message("Template sent successfully")
                return

            api_error = _extract_api_error(body)
            if api_error:
                hint = _suggest_fix(api_error)
                error_text = (
                    f"Failed to send template: HTTP {resp.status_code}. "
                    f"error={{code: {api_error.get('code')}, type: {api_error.get('type')}, "
                    f"message: {api_error.get('message')}, subcode: {api_error.get('error_subcode')}}}. "
                    f"hint: {hint}"
                )
                yield self.create_text_message(error_text)
            else:
                yield self.create_text_message(f"Failed to send template: HTTP {resp.status_code}")
        except Exception as e:
            yield self.create_text_message(f"Failed to send template due to exception: {str(e)}")


