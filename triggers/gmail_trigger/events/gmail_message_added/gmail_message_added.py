from __future__ import annotations

import base64
import binascii
import json
import quopri
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event
from dify_plugin.invocations.file import UploadFileResponse


class GmailMessageAddedEvent(Event):
    _GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
    _MAX_ATTACHMENT_UPLOAD_COUNT = 20
    _MAX_ATTACHMENT_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MiB

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        # Prefer payload delivered from Trigger.dispatch_event
        history_id = payload.get("historyId")
        items: list[dict[str, Any]] = []
        raw_items = payload.get("message_added") or payload.get("items")
        if isinstance(raw_items, list):
            items = raw_items  # type: ignore[assignment]

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
            attachments_meta: list[Mapping[str, Any]] = []
            inline_parts: list[Mapping[str, Any]] = []

            def _walk_parts(part: Mapping[str, Any] | None):
                nonlocal has_attachments, attachments_meta, inline_parts
                if not part:
                    return
                filename = part.get("filename")
                body = part.get("body") or {}
                if not isinstance(body, Mapping):
                    body = {}
                mime_type = part.get("mimeType")
                if filename:
                    has_attachments = True
                    attachment_id = body.get("attachmentId")
                    size = body.get("size")
                    inline_data = body.get("data")
                    original_url: str | None = (
                        f"{self._GMAIL_BASE}/users/me/messages/{mid_str}/attachments/{attachment_id}"
                        if attachment_id
                        else None
                    )
                    attachments_meta.append(
                        {
                            "filename": filename,
                            "mimeType": mime_type,
                            "size": size,
                            "attachmentId": attachment_id,
                            "original_url": original_url,
                            "inline_data": inline_data,
                        }
                    )
                elif mime_type in {"text/plain", "text/html"}:
                    inline_data = body.get("data")
                    if inline_data:
                        inline_parts.append(
                            {
                                "mimeType": mime_type,
                                "data": inline_data,
                                "headers": part.get("headers") or [],
                            }
                        )
                for p in (part.get("parts") or []) or []:
                    _walk_parts(p)

            _walk_parts(m.get("payload") or {})

            existing_urls: set[str] = {
                str(meta.get("original_url")) for meta in attachments_meta if isinstance(meta.get("original_url"), str)
            }
            external_attachments = self._extract_external_attachment_links(
                inline_parts=inline_parts,
                existing_urls=existing_urls,
            )
            if external_attachments:
                has_attachments = True
                attachments_meta.extend(external_attachments)

            # If label filters configured, enforce OR semantics (any match)
            msg_label_ids: list[str] = m.get("labelIds") or []
            if selected and not (selected.intersection(msg_label_ids)):
                continue

            processed_attachments: list[dict[str, Any]] = self._prepare_attachments(
                message_id=mid_str,
                attachments=attachments_meta,
                headers=headers,
            )

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
                    "attachments": processed_attachments,
                }
            )

        if not messages:
            raise EventIgnoreError()

        return Variables(variables={"history_id": str(history_id or ""), "messages": messages})

    def _extract_external_attachment_links(
        self,
        inline_parts: list[Mapping[str, Any]],
        existing_urls: set[str],
    ) -> list[dict[str, Any]]:
        attachments: dict[str, dict[str, Any]] = {}
        for part in inline_parts:
            data = part.get("data")
            if not isinstance(data, str):
                continue
            try:
                raw_bytes = self._decode_base64url(data)
            except binascii.Error:
                continue

            headers_list = part.get("headers") if isinstance(part.get("headers"), list) else []
            decoded_bytes = self._decode_transfer_encoding(raw_bytes, headers_list)

            mime_type = str(part.get("mimeType") or "")
            text_content = decoded_bytes.decode("utf-8", errors="ignore")

            if mime_type == "text/html":
                candidates = self._extract_links_from_html(text_content)
            else:
                candidates = [(url, None) for url in self._extract_links_from_text(text_content)]

            for url, label in candidates:
                if not isinstance(url, str):
                    continue
                normalized_url = url.strip()
                if not normalized_url:
                    continue
                if normalized_url in existing_urls or normalized_url in attachments:
                    continue
                if not self._is_supported_external_url(normalized_url):
                    continue
                filename = (label or "").strip() or self._derive_filename_from_url(normalized_url)
                attachments[normalized_url] = {
                    "filename": filename or "attachment",
                    "mimeType": "application/octet-stream",
                    "size": None,
                    "attachmentId": None,
                    "original_url": normalized_url,
                    "inline_data": None,
                }

        return list(attachments.values())

    def _prepare_attachments(
        self,
        message_id: str,
        attachments: list[Mapping[str, Any]],
        headers: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        processed: list[dict[str, Any]] = []
        upload_candidates = sum(
            1
            for meta in attachments
            if isinstance(meta, Mapping) and (meta.get("attachmentId") or meta.get("inline_data"))
        )
        allow_upload = upload_candidates <= self._MAX_ATTACHMENT_UPLOAD_COUNT

        for meta in attachments:
            attachment: dict[str, Any] = dict(meta)
            attachment.setdefault("original_url", None)
            attachment.setdefault("size", None)
            inline_data = attachment.pop("inline_data", None)
            attachment["file_url"] = None
            attachment["upload_file_id"] = None
            attachment["file_source"] = "gmail"

            if not allow_upload:
                attachment["file_url"] = attachment.get("original_url")
                self._finalize_attachment_urls(attachment)
                processed.append(attachment)
                continue

            size_hint_raw = attachment.get("size")
            size_hint = size_hint_raw if isinstance(size_hint_raw, int) else None

            if isinstance(size_hint, int) and size_hint > self._MAX_ATTACHMENT_UPLOAD_SIZE:
                attachment["file_url"] = attachment.get("original_url")
                self._finalize_attachment_urls(attachment)
                processed.append(attachment)
                continue

            content, resolved_size = self._fetch_attachment_content(
                message_id=message_id,
                attachment=attachment,
                inline_data=inline_data,
                headers=headers,
            )
            actual_size = resolved_size if isinstance(resolved_size, int) else None
            if actual_size is None and content is not None:
                actual_size = len(content)

            if actual_size is not None:
                attachment["size"] = actual_size

            if content is None or (actual_size is not None and actual_size > self._MAX_ATTACHMENT_UPLOAD_SIZE):
                attachment["file_url"] = attachment.get("original_url")
                self._finalize_attachment_urls(attachment)
                processed.append(attachment)
                continue

            upload_response = self._upload_to_storage(
                filename=attachment.get("filename") or "attachment",
                content=content,
                mimetype=attachment.get("mimeType") or "application/octet-stream",
            )
            if upload_response:
                attachment["upload_file_id"] = upload_response.id
                if upload_response.preview_url:
                    attachment["file_url"] = upload_response.preview_url
                    attachment["file_source"] = "dify_storage"
                else:
                    attachment["file_url"] = attachment.get("original_url")
            else:
                attachment["file_url"] = attachment.get("original_url")

            self._finalize_attachment_urls(attachment)
            processed.append(attachment)

        return processed

    def _fetch_attachment_content(
        self,
        message_id: str,
        attachment: Mapping[str, Any],
        inline_data: str | None,
        headers: Mapping[str, str],
    ) -> tuple[bytes | None, int | None]:
        if inline_data:
            try:
                content = self._decode_base64url(inline_data)
            except binascii.Error:
                return None, None
            return content, len(content)

        attachment_id = attachment.get("attachmentId")
        if not attachment_id:
            return None, None

        url = f"{self._GMAIL_BASE}/users/me/messages/{message_id}/attachments/{attachment_id}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except requests.RequestException:
            return None, None
        if response.status_code != 200:
            return None, None

        data = response.json() or {}
        encoded = data.get("data")
        if not encoded:
            return None, None

        try:
            content = self._decode_base64url(encoded)
        except binascii.Error:
            return None, None

        size = data.get("size")
        size_value = size if size is not None else len(content)
        return content, size_value

    @staticmethod
    def _finalize_attachment_urls(attachment: dict[str, Any]) -> None:
        original_url = attachment.get("original_url")
        file_url = attachment.get("file_url")
        if not isinstance(original_url, str) or original_url == file_url:
            attachment.pop("original_url", None)

    def _upload_to_storage(self, filename: str, content: bytes, mimetype: str) -> UploadFileResponse | None:
        # runtime.session.file is available only during actual execution
        runtime = self.runtime
        if runtime is None:
            return None

        try:
            file_invocation = runtime.session.file
        except AttributeError:
            return None

        if file_invocation is None:
            return None

        try:
            return file_invocation.upload(filename=filename, content=content, mimetype=mimetype)
        except Exception:
            return None

    @staticmethod
    def _decode_base64url(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)

    @staticmethod
    def _decode_transfer_encoding(content: bytes, headers: list[Mapping[str, Any]] | None) -> bytes:
        encoding: str | None = None
        for header in headers or []:
            name = header.get("name")
            if isinstance(name, str) and name.lower() == "content-transfer-encoding":
                value = header.get("value")
                if isinstance(value, str):
                    encoding = value.lower()
                break
        if encoding and "quoted-printable" in encoding:
            return quopri.decodestring(content)
        return content

    def _extract_links_from_html(self, html: str) -> list[tuple[str, str | None]]:
        class _AttachmentLinkParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links: list[tuple[str, str | None]] = []
                self._current_href: str | None = None
                self._text_buffer: list[str] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag.lower() != "a":
                    return
                attr_map = {k: v for k, v in attrs if k}
                href = attr_map.get("href")
                if not href:
                    return
                self._current_href = href
                self._text_buffer = []
                aria_label = attr_map.get("aria-label")
                if aria_label:
                    self._text_buffer.append(aria_label)

            def handle_data(self, data: str) -> None:
                if self._current_href is not None:
                    self._text_buffer.append(data)

            def handle_endtag(self, tag: str) -> None:
                if tag.lower() != "a":
                    return
                if self._current_href is None:
                    return
                text = "".join(self._text_buffer).strip() or None
                self.links.append((self._current_href, text))
                self._current_href = None
                self._text_buffer = []

        parser = _AttachmentLinkParser()
        try:
            parser.feed(html)
        except Exception:
            return []
        return parser.links

    @staticmethod
    def _extract_links_from_text(text: str) -> list[str]:
        url_pattern = re.compile(r"https?://[^\s<>\"']+")
        return url_pattern.findall(text)

    @staticmethod
    def _is_supported_external_url(url: str) -> bool:
        parsed = urlparse(url)
        hostname = (parsed.netloc or "").lower()
        if not hostname:
            return False
        allowed_hosts = {
            "drive.google.com",
            "docs.google.com",
        }
        if hostname in allowed_hosts:
            return True
        # Allow subdomains under google.com that serve Drive content.
        return hostname.endswith(".google.com") and ("drive" in hostname or "docs" in hostname)

    @staticmethod
    def _derive_filename_from_url(url: str) -> str:
        parsed = urlparse(url)
        candidate = parsed.path.rsplit("/", 1)[-1] if parsed.path else ""
        candidate = unquote(candidate)
        if candidate and candidate not in {"view", "open", "download", "uc"}:
            return candidate
        return "attachment"
