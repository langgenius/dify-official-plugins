"""
The operations behind the ``gmail_*`` tools. Each takes the Google context and the tool parameters
and returns (output variables, JSON message, text message); ``run`` handles credentials and errors,
so every tool file is a thin wrapper (Dify loads one Tool class per file).
"""

import base64
import html
import re
from email.message import EmailMessage
from email.utils import getaddresses
from typing import Any, Callable, Mapping

from tools.google_client import GoogleAuthError, GoogleContext, google_request, json_of, require, resolve_context, segment

API = "https://gmail.googleapis.com/gmail/v1/users/me"
# Labels Gmail defines for every mailbox; they are given by ID, not looked up by name.
SYSTEM_LABELS = {"INBOX", "SPAM", "TRASH", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT",
                 "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
MAX_BODY = 20_000

Result = tuple[dict[str, Any], Any, str]


def run(tool: Any, params: Mapping[str, Any], op: Callable[[GoogleContext, Mapping[str, Any]], Result]):
    try:
        ctx = resolve_context(tool.runtime.credentials, tool)
        out, data, text = op(ctx, params)
    except GoogleAuthError as e:
        yield tool.create_text_message(str(e))
        return
    tool._out.update(out, success=True)
    yield tool.create_json_message(data)
    yield tool.create_text_message(text)


# ── message helpers ──────────────────────────────────────────────────


def _headers(payload: Mapping[str, Any]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers") or []}


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _body_text(payload: Mapping[str, Any]) -> str:
    """The plain-text body of a message payload (HTML is reduced to text when there is no plain part)."""
    plain, rich = [], []

    def walk(part: Mapping[str, Any]) -> None:
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain" and not part.get("filename"):
            plain.append(_decode(data))
        elif data and mime == "text/html" and not part.get("filename"):
            rich.append(_decode(data))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    text = re.sub(r"<(br|/p|/div|/li)[^>]*>", "\n", "\n".join(rich), flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def message_dict(message: Mapping[str, Any], with_body: bool = True) -> dict[str, Any]:
    payload = message.get("payload") or {}
    headers = _headers(payload)
    result = {
        "id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": html.unescape(message.get("snippet", "")),
        "labels": list(message.get("labelIds") or []),
        "unread": "UNREAD" in (message.get("labelIds") or []),
    }
    if with_body:
        body = _body_text(payload)
        result["body"] = body if len(body) <= MAX_BODY else body[:MAX_BODY] + "\n[… truncated]"
    return result


def _raw(message: EmailMessage) -> str:
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def _my_address(ctx: GoogleContext) -> str:
    return json_of(google_request(ctx, "GET", f"{API}/profile")).get("emailAddress", "").lower()


def label_ids(ctx: GoogleContext, names: Any, create_missing: bool = False) -> list[str]:
    """Label IDs for a comma-separated list of label names or IDs (system labels such as STARRED by ID)."""
    wanted = [n.strip() for n in str(names or "").split(",") if n.strip()]
    if not wanted:
        return []
    labels = json_of(google_request(ctx, "GET", f"{API}/labels")).get("labels") or []
    by_name = {label.get("name", "").lower(): label.get("id") for label in labels}
    ids = {label.get("id") for label in labels}
    result = []
    for name in wanted:
        if name in ids or name.upper() in SYSTEM_LABELS:
            result.append(name if name in ids else name.upper())
        elif name.lower() in by_name:
            result.append(by_name[name.lower()])
        elif create_missing:
            result.append(json_of(google_request(ctx, "POST", f"{API}/labels", json_body={"name": name})).get("id"))
        else:
            raise GoogleAuthError(f"No label named '{name}'. Use gmail_list_labels to see the labels.")
    return result


# ── messages ─────────────────────────────────────────────────────────


def reply(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Reply in the original message's thread, keeping the conversation headers."""
    message_id, body = require(p, "message_id", "body")
    original = json_of(google_request(ctx, "GET", f"{API}/messages/{segment(message_id)}", params={
        "format": "metadata",
        "metadataHeaders": ["From", "To", "Cc", "Reply-To", "Subject", "Message-ID", "References"],
    }))
    headers = _headers(original.get("payload") or {})
    me = _my_address(ctx)
    to = [a for _, a in getaddresses([headers.get("reply-to") or headers.get("from", "")]) if a]
    cc: list[str] = []
    if p.get("reply_all"):
        others = [a for _, a in getaddresses([headers.get("to", ""), headers.get("cc", "")]) if a]
        cc = [a for a in dict.fromkeys(others) if a.lower() != me and a not in to]
    if to and to[0].lower() == me:
        # Replying to a message we sent: answer its recipients instead.
        to = [a for _, a in getaddresses([headers.get("to", "")]) if a and a.lower() != me] or to
    subject = headers.get("subject", "")
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if headers.get("message-id"):
        msg["In-Reply-To"] = headers["message-id"]
        msg["References"] = (headers.get("references", "") + " " + headers["message-id"]).strip()
    msg.set_content(str(body))
    if p.get("body_html"):
        msg.add_alternative(str(p["body_html"]), subtype="html")
    sent = json_of(google_request(ctx, "POST", f"{API}/messages/send",
                                  json_body={"raw": _raw(msg), "threadId": original.get("threadId")}))
    return ({"message_id": sent.get("id", ""), "thread_id": sent.get("threadId", "")},
            {"id": sent.get("id", ""), "thread_id": sent.get("threadId", ""), "to": to, "cc": cc},
            f"Replied to {', '.join(to)}" + (f" (cc {', '.join(cc)})" if cc else "") + f": {msg['Subject']}")


def trash_message(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (message_id,) = require(p, "message_id")
    action = "untrash" if p.get("restore") else "trash"
    google_request(ctx, "POST", f"{API}/messages/{segment(message_id)}/{action}")
    done = "Restored the message from the trash." if action == "untrash" else "Moved the message to the trash (it is deleted after 30 days)."
    return {"message_id": message_id}, {"message_id": message_id, "action": action}, done


def mark_read(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (message_id,) = require(p, "message_id")
    read = p.get("read") is not False and str(p.get("read")).lower() != "false"
    body = {"removeLabelIds": ["UNREAD"]} if read else {"addLabelIds": ["UNREAD"]}
    message = json_of(google_request(ctx, "POST", f"{API}/messages/{segment(message_id)}/modify", json_body=body))
    return ({"message_id": message_id, "unread": "UNREAD" in (message.get("labelIds") or [])}, message,
            f"Marked the message as {'read' if read else 'unread'}.")


def modify_labels(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Add or remove labels on a message, or on a whole thread when thread_id is given."""
    target_id = str(p.get("thread_id") or p.get("message_id") or "").strip()
    if not target_id:
        raise GoogleAuthError("message_id or thread_id is required.")
    kind = "threads" if p.get("thread_id") else "messages"
    add = label_ids(ctx, p.get("add_labels"), create_missing=bool(p.get("create_missing")))
    remove = label_ids(ctx, p.get("remove_labels"))
    if not add and not remove:
        raise GoogleAuthError("Give add_labels and/or remove_labels.")
    result = json_of(google_request(ctx, "POST", f"{API}/{kind}/{segment(target_id)}/modify",
                                    json_body={"addLabelIds": add, "removeLabelIds": remove}))
    labels = result.get("labelIds") or sorted({l for m in result.get("messages") or [] for l in m.get("labelIds") or []})
    return ({"labels": labels}, {"id": target_id, "labels": labels},
            f"Labels on the {kind[:-1]} are now: {', '.join(labels) or 'none'}.")


# ── labels ───────────────────────────────────────────────────────────


def list_labels(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    labels = [{"id": l.get("id", ""), "name": l.get("name", ""), "type": l.get("type", "")}
              for l in json_of(google_request(ctx, "GET", f"{API}/labels")).get("labels") or []]
    labels.sort(key=lambda l: (l["type"] != "user", l["name"].lower()))
    user = [l for l in labels if l["type"] == "user"]
    return ({"labels": labels, "count": len(labels)}, {"labels": labels},
            f"{len(labels)} labels. Your own: " + (", ".join(l["name"] for l in user) or "none"))


def create_label(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (name,) = require(p, "name")
    body: dict[str, Any] = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    if p.get("background_color") and p.get("text_color"):
        body["color"] = {"backgroundColor": p["background_color"], "textColor": p["text_color"]}
    label = json_of(google_request(ctx, "POST", f"{API}/labels", json_body=body))
    return {"label_id": label.get("id", "")}, label, f"Created label '{label.get('name', name)}'."


def delete_label(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (label,) = require(p, "label")
    (label_id,) = label_ids(ctx, label)
    if label_id in SYSTEM_LABELS:
        raise GoogleAuthError(f"{label_id} is a system label and cannot be deleted.")
    google_request(ctx, "DELETE", f"{API}/labels/{segment(label_id)}")
    return {"deleted": True}, {"label_id": label_id, "deleted": True}, f"Deleted the label '{label}' (messages keep their other labels)."


# ── threads ──────────────────────────────────────────────────────────


def get_thread(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (thread_id,) = require(p, "thread_id")
    thread = json_of(google_request(ctx, "GET", f"{API}/threads/{segment(thread_id)}", params={"format": "full"}))
    messages = [message_dict(m) for m in thread.get("messages") or []]
    text = "\n\n".join(f"From: {m['from']}\nDate: {m['date']}\nSubject: {m['subject']}\n\n{m['body']}" for m in messages)
    return ({"messages": messages, "count": len(messages), "subject": messages[0]["subject"] if messages else ""},
            {"thread_id": thread_id, "messages": messages}, text or "The thread is empty.")


def trash_thread(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (thread_id,) = require(p, "thread_id")
    action = "untrash" if p.get("restore") else "trash"
    google_request(ctx, "POST", f"{API}/threads/{segment(thread_id)}/{action}")
    done = "Restored the conversation from the trash." if action == "untrash" else "Moved the whole conversation to the trash."
    return {"thread_id": thread_id}, {"thread_id": thread_id, "action": action}, done


# ── drafts ───────────────────────────────────────────────────────────


def get_draft(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (draft_id,) = require(p, "draft_id")
    draft = json_of(google_request(ctx, "GET", f"{API}/drafts/{segment(draft_id)}", params={"format": "full"}))
    message = message_dict(draft.get("message") or {})
    message["draft_id"] = draft.get("id", draft_id)
    return ({"draft": message, "subject": message["subject"], "to": message["to"], "body": message["body"]}, message,
            f"To: {message['to']}\nSubject: {message['subject']}\n\n{message['body']}")


def delete_draft(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (draft_id,) = require(p, "draft_id")
    google_request(ctx, "DELETE", f"{API}/drafts/{segment(draft_id)}")
    return {"deleted": True}, {"draft_id": draft_id, "deleted": True}, f"Deleted draft {draft_id}."
