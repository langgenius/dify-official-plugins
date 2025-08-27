from collections.abc import Generator
from typing import Any, Optional

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendDraftTool(Tool):
    """
    Sends an existing Gmail draft.

    Primary path:
      POST https://gmail.googleapis.com/gmail/v1/users/me/drafts/send
      body: {"id": "<draft_id>"}

    Hardening:
      If the provided identifier is actually a MESSAGE id (with DRAFT label),
      we list drafts and map message.id -> draft.id, then send.
    """

    # ---------------------------
    # Main entry
    # ---------------------------
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            # ---- Inputs ----
            draft_id_or_message_id = (tool_parameters.get("draft_id") or "").strip()
            if not draft_id_or_message_id:
                yield self.create_text_message("Error: Draft ID is required.")
                return

            # ---- Auth ----
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Error: No access token available. Please authorize the Gmail integration.")
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # Try to send assuming it's a proper DRAFT id
            yield self.create_text_message(f"Sending draft {draft_id_or_message_id}...")
            send_result = self._send_draft_by_id(headers, draft_id_or_message_id)

            if isinstance(send_result, dict):
                # Success on first try
                yield self.create_text_message("Draft sent successfully!")
                
                # Create specific output variables for workflow referencing
                yield self.create_variable_message("draft_id", draft_id_or_message_id)
                yield self.create_variable_message("message_id", send_result.get("id"))
                yield self.create_variable_message("thread_id", send_result.get("threadId"))
                
                yield self.create_json_message({
                    "status": "success",
                    "draft_id": draft_id_or_message_id,
                    "message_id": send_result.get("id"),
                    "thread_id": send_result.get("threadId"),
                })
                return

            # If the first attempt failed due to not found/invalid, try to treat it as MESSAGE id
            if send_result in ("not_found", "invalid"):
                # Check if this is actually a message id of a draft
                yield self.create_text_message("Draft not found by ID; checking if the provided value is a MESSAGE id...")
                mapped_draft_id = self._map_message_id_to_draft_id(headers, draft_id_or_message_id)

                if not mapped_draft_id:
                    # Provide actionable guidance
                    yield self.create_text_message(
                        "Error: Draft not found. The value provided doesn't match any draft id, "
                        "and it doesn't map to a draft message. Ensure you're passing the Gmail draft id "
                        "(not a message id or an Outlook/Graph id)."
                    )
                    return

                yield self.create_text_message(f"Found matching draft id '{mapped_draft_id}' for the provided message id; sending...")
                send_result2 = self._send_draft_by_id(headers, mapped_draft_id)
                if isinstance(send_result2, dict):
                    yield self.create_text_message("Draft sent successfully!")
                    
                    # Create specific output variables for workflow referencing
                    yield self.create_variable_message("draft_id", mapped_draft_id)
                    yield self.create_variable_message("message_id", send_result2.get("id"))
                    yield self.create_variable_message("thread_id", send_result2.get("threadId"))
                    
                    yield self.create_json_message({
                        "status": "success",
                        "draft_id": mapped_draft_id,
                        "message_id": send_result2.get("id"),
                        "thread_id": send_result2.get("threadId"),
                        "note": "Original input appeared to be a message id; mapped to draft id automatically.",
                    })
                    return

                # Fall-through: second attempt failed too
                self._emit_send_error(send_result2)
                return

            # Other errors (auth/network/unknown)
            self._emit_send_error(send_result)
            return

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error sending draft: {str(e)}")

    # ---------------------------
    # Helpers
    # ---------------------------
    def _send_draft_by_id(self, headers: dict, draft_id: str) -> dict | str:
        """
        Try to send a draft by id.
        Returns:
          - dict (the sent Message resource) on success
          - "unauthorized" | "forbidden" | "not_found" | "invalid" | "api_error:<status>:<text>"
        """
        send_url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts/send"
        try:
            resp = requests.post(send_url, headers=headers, json={"id": draft_id}, timeout=60)
        except requests.RequestException as e:
            return f"api_error:network:{e}"

        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {"id": None, "threadId": None}

        if resp.status_code == 401:
            return "unauthorized"
        if resp.status_code == 403:
            return "forbidden"
        if resp.status_code == 404:
            return "not_found"
        if resp.status_code == 400:
            # Gmail often returns 400 when the id doesn't parse as a draft id
            return "invalid"

        return f"api_error:{resp.status_code}:{resp.text}"

    def _map_message_id_to_draft_id(self, headers: dict, possible_message_id: str) -> Optional[str]:
        """
        If the caller mistakenly passed a MESSAGE id (with DRAFT label),
        find the corresponding draft.id by listing drafts and matching message.id.

        Returns draft.id or None if not found.
        """
        # 1) Check if it is a message and has DRAFT label
        msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{possible_message_id}?format=metadata"
        try:
            r = requests.get(msg_url, headers=headers, timeout=60)
        except requests.RequestException:
            return None

        if r.status_code != 200:
            return None

        msg = r.json()
        if "DRAFT" not in (msg.get("labelIds") or []):
            return None  # It's a message, but not a draft

        # 2) Iterate drafts and match message.id
        page_token = None
        while True:
            list_url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
            params = {"maxResults": 500}
            if page_token:
                params["pageToken"] = page_token

            try:
                dr = requests.get(list_url, headers=headers, params=params, timeout=60)
            except requests.RequestException:
                return None

            if dr.status_code != 200:
                return None

            data = dr.json() or {}
            for d in data.get("drafts", []) or []:
                message = d.get("message") or {}
                if message.get("id") == possible_message_id:
                    return d.get("id")

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return None

    def _emit_send_error(self, code: str) -> Generator[ToolInvokeMessage, None, None]:
        """
        Convert error code string into a helpful user message.
        """
        if code == "unauthorized":
            yield self.create_text_message("Error: Access token expired or invalid. Please re-authorize the Gmail integration.")
        elif code == "forbidden":
            yield self.create_text_message("Error: Access denied. Ensure the token has Gmail scopes that allow sending (e.g., gmail.send).")
        elif code == "not_found":
            yield self.create_text_message(
                "Error: Draft not found. Make sure you pass the **draft id** returned by drafts.create/update "
                "(not a message id or an Outlook/Graph id)."
            )
        elif code == "invalid":
            yield self.create_text_message(
                "Error: The provided id isn't a valid Gmail draft id. If you passed a message id, use the draft id instead."
            )
        elif isinstance(code, str) and code.startswith("api_error:"):
            _, status, text = (code.split(":", 2) + ["", ""])[:3]
            yield self.create_text_message(f"Error: Gmail API returned status {status}: {text}")
        else:
            yield self.create_text_message("Error: Failed to send draft due to an unknown error.")
