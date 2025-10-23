import re
from typing import Optional, Generator
import requests
from dify_plugin.interfaces.tool import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendMessageTool(Tool):
    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        access_token: str = (self.runtime.credentials.get("access_token") or "").strip()
        phone_number_id: str = (self.runtime.credentials.get("phone_number_id") or "").strip()

        to_raw: str = (tool_parameters.get("to") or "").strip()
        text: str = (tool_parameters.get("text") or "").strip()

        if not access_token or not phone_number_id:
            details = f"have_access_token={bool(access_token)}, have_phone_number_id={bool(phone_number_id)}"
            yield self.create_text_message(
                f"Configuration error: missing WhatsApp credentials ({details})"
            )
            return

        # ---- Helper: normalize to E.164 digits (no '+') ----
        def _digits_only(s: str) -> str:
            return re.sub(r"[^0-9]", "", s or "")

        # ---- Helper: try to parse the actual WhatsApp webhook envelope ----
        def _extract_from_whatsapp_webhook_envelope(d: dict) -> Optional[str]:
            """
            Handle the JSON shape:
            {
              "object": "whatsapp_business_account",
              "entry": [
                {
                  "changes": [
                    {
                      "value": {
                        "contacts": [{"wa_id": "..."}],
                        "messages": [{"from": "..."}]
                      }
                    }
                  ]
                }
              ]
            }
            Prefer messages[0].from, else contacts[0].wa_id
            """
            try:
                entries = d.get("entry") or []
                for entry in entries:
                    changes = entry.get("changes") or []
                    for change in changes:
                        value = change.get("value") or {}
                        # Prefer message.from
                        messages = value.get("messages") or []
                        if isinstance(messages, list) and messages:
                            frm = (messages[0] or {}).get("from")
                            if isinstance(frm, str) and frm.strip():
                                return frm.strip()
                        # Fallback to contacts[0].wa_id
                        contacts = value.get("contacts") or []
                        if isinstance(contacts, list) and contacts:
                            wa_id = (contacts[0] or {}).get("wa_id")
                            if isinstance(wa_id, str) and wa_id.strip():
                                return wa_id.strip()
            except Exception:
                pass
            return None

        # ---- Helper: handle flattened value (if someone stored just the inner 'value') ----
        def _extract_from_value_only(d: dict) -> Optional[str]:
            try:
                value = d.get("value") or {}
                # Prefer message.from
                messages = value.get("messages") or []
                if isinstance(messages, list) and messages:
                    frm = (messages[0] or {}).get("from")
                    if isinstance(frm, str) and frm.strip():
                        return frm.strip()
                # Fallback to contacts[0].wa_id
                contacts = value.get("contacts") or []
                if isinstance(contacts, list) and contacts:
                    wa_id = (contacts[0] or {}).get("wa_id")
                    if isinstance(wa_id, str) and wa_id.strip():
                        return wa_id.strip()
            except Exception:
                pass
            return None

        # If recipient is not explicitly provided, try to infer it from runtime context
        if not to_raw:
            
                pass

        if not to_raw or not text:
            yield self.create_text_message(
                "Missing required parameters: text (and recipient could not be inferred)"
            )
            return

        # Normalize recipient: WhatsApp Cloud API expects full international number without '+'
        to = _digits_only(to_raw)
        if not to:
            yield self.create_text_message("Recipient phone/wa_id could not be normalized to digits.")
            return

        url = f"https://graph.facebook.com/v24.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,                # digits only
            "type": "text",
            "text": {"body": text},
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            body = safe_json(resp)
            ok = 200 <= resp.status_code < 300

            if ok:
                try:
                    wa_message_id = None
                    if isinstance(body, dict):
                        msgs = body.get("messages") or []
                        if isinstance(msgs, list) and msgs:
                            wa_message_id = msgs[0].get("id")
                    yield self.create_text_message(f"Message sent to {to} with ID: {wa_message_id}")
                except Exception:
                    summary = f"sent to {to}"
                    yield self.create_text_message(summary)
                return

            # Provide actionable error feedback
            api_error = extract_api_error(body)
            if api_error:
                hint = suggest_fix(api_error)
                error_text = (
                    f"Failed to send message: HTTP {resp.status_code}. "
                    f"error={{code: {api_error.get('code')}, type: {api_error.get('type')}, "
                    f"message: {api_error.get('message')}, subcode: {api_error.get('error_subcode')}}}. "
                    f"hint: {hint}"
                )
                yield self.create_text_message(error_text)
            else:
                yield self.create_text_message(f"Failed to send message: HTTP {resp.status_code}")

        except Exception as e:
            yield self.create_text_message(f"Failed to send message due to exception: {str(e)}")



def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text[:500]}


def extract_api_error(body: dict):
    if isinstance(body, dict) and "error" in body:
        err = body.get("error") or {}
        return {
            "code": err.get("code"),
            "type": err.get("type"),
            "message": err.get("message"),
            "error_subcode": err.get("error_subcode"),
        }
    return None


def suggest_fix(api_error: dict) -> str:
    code = api_error.get("code")
    subcode = api_error.get("error_subcode")
    message = api_error.get("message") or ""

    # Common Graph API errors for WhatsApp Cloud
    if code == 190:
        return "Invalid or expired access token. Recreate a system user token with proper permissions."
    if code == 100:
        return "Invalid parameters. Verify 'phone_number_id' and that 'to' is a valid international number."
    if subcode in {2018049, 131000, 131031}:
        return (
            "Recipient has not messaged your business recently or is not opted-in. "
            "Ensure a recent user-initiated session or use an approved template."
        )
    if "Unsupported post request" in message:
        return "Check that the phone_number_id belongs to your app and Business Account."

    return "Check Business Account setup, permissions (whatsapp_business_messaging), and recipient format (E.164 without '+')."


