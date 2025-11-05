from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class GmailMessageAddedEvent(Event):
    _GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        # Prefer payload delivered from Trigger.dispatch_event
        history_id = payload.get("historyId")
        items: list[dict[str, Any]] = []
        raw_items = payload.get("message_added") or payload.get("items")
        if isinstance(raw_items, list):
            items = [it for it in raw_items if isinstance(it, Mapping)]  # type: ignore[typeddict-item]

        # Fallback to storage (legacy path)
        if not items:
            sub_key = (self.runtime.subscription.properties or {}).get("subscription_key") or ""
            pending_key = f"gmail:{sub_key}:pending:message_added"

            if not self.runtime.session.storage.exist(pending_key):
                raise EventIgnoreError()

            raw_bytes = self.runtime.session.storage.get(pending_key)
            try:
                data = json.loads(raw_bytes.decode("utf-8"))
            except Exception:
                # Corrupted payload, cleanup and ignore
                self.runtime.session.storage.delete(pending_key)
                raise EventIgnoreError()

            # Cleanup the pending batch to avoid re-processing
            self.runtime.session.storage.delete(pending_key)

            items = data.get("items") or []
            history_id = history_id or data.get("historyId")

        if not items:
            raise EventIgnoreError()

        # Fetch message details for each id
        access_token: str | None = (self.runtime.credentials or {}).get("access_token")
        if not access_token:
            raise ValueError("Missing access token")
        headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}

        # Optional label-based local filtering
        prop_label_ids: list[str] = (self.runtime.subscription.properties or {}).get("label_ids") or []
        selected: set[str] = set(prop_label_ids)

        messages: list[dict[str, Any]] = []
        for it in items:
            mid = it.get("id")
            if not mid:
                continue
            mid_str = str(mid)
            murl = f"{self._GMAIL_BASE}/users/me/messages/{mid_str}"
            mparams: dict[str, str] = {"format": "full"}
            mresp: requests.Response = requests.get(murl, headers=headers, params=mparams, timeout=10)
            if mresp.status_code != 200:
                continue
            m = mresp.json() or {}
            headers_list = (m.get("payload") or {}).get("headers") or []
            headers_map = {h.get("name"): h.get("value") for h in headers_list if h.get("name")}

            has_attachments = False
            attachments_meta: list[dict[str, Any]] = []

            def _walk_parts(part: Mapping[str, Any] | None):
                nonlocal has_attachments, attachments_meta
                if not part:
                    return
                filename = part.get("filename")
                if filename:
                    has_attachments = True
                    body = part.get("body")
                    attachment_id: str | None = None
                    size: Any = None
                    if isinstance(body, Mapping):
                        raw_attachment_id = body.get("attachmentId")
                        if isinstance(raw_attachment_id, str):
                            attachment_id = raw_attachment_id
                        size = body.get("size")
                    download_url: str | None = (
                        f"{self._GMAIL_BASE}/users/me/messages/{mid_str}/attachments/{attachment_id}"
                        if attachment_id
                        else None
                    )
                    attachments_meta.append(
                        {
                            "filename": filename,
                            "mimeType": part.get("mimeType"),
                            "size": size,
                            "attachmentId": attachment_id,
                            "download_url": download_url,
                        }
                    )
                for p in (part.get("parts") or []) or []:
                    _walk_parts(p)

            _walk_parts(m.get("payload") or {})

            # If label filters configured, enforce OR semantics (any match)
            msg_label_ids: list[str] = m.get("labelIds") or []
            if selected and not (selected.intersection(msg_label_ids)):
                continue

            messages.append(
                {
                    "id": m.get("id"),
                    "threadId": m.get("threadId"),
                    "internalDate": m.get("internalDate"),
                    "snippet": m.get("snippet"),
                    "sizeEstimate": m.get("sizeEstimate"),
                    "labelIds": m.get("labelIds") or [],
                    "headers": {
                        "From": headers_map.get("From"),
                        "To": headers_map.get("To"),
                        "Subject": headers_map.get("Subject"),
                        "Date": headers_map.get("Date"),
                        "Message-Id": headers_map.get("Message-Id"),
                    },
                    "has_attachments": has_attachments,
                    "attachments": attachments_meta,
                }
            )

        if not messages:
            raise EventIgnoreError()

        return Variables(variables={"history_id": str(history_id or ""), "messages": messages})
