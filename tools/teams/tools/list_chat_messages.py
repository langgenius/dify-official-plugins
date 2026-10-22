from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import (
    GraphError,
    bounded_int,
    check_next_link,
    paginate,
    require,
    resolve_graph_context,
    segment,
)

_TIME_FIELDS = ("createdDateTime", "lastModifiedDateTime")


def _utc(value: str, name: str) -> str:
    """An ISO 8601 date-time with an explicit offset, as UTC for an OData filter."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise GraphError(f"{name} must be an ISO 8601 date-time with a time zone, e.g. 2026-10-14T00:00:00+09:00.") from e
    if parsed.tzinfo is None:
        raise GraphError(f"{name} must include a time zone, e.g. 2026-10-14T00:00:00+09:00.")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ListChatMessagesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (chat_id,) = require(tool_parameters, "chat_id")
            top = bounded_int(tool_parameters.get("top"), 20, 1, 50, "top")
            max_pages = bounded_int(tool_parameters.get("max_pages"), 5, 1, 10, "max_pages")
            time_field = (tool_parameters.get("time_field") or "createdDateTime").strip()
            if time_field not in _TIME_FIELDS:
                raise GraphError("time_field must be createdDateTime or lastModifiedDateTime.")
            start = (tool_parameters.get("start_datetime") or "").strip()
            end = (tool_parameters.get("end_datetime") or "").strip()
            include_system = bool(tool_parameters.get("include_system_events"))
            next_link = (tool_parameters.get("next_link") or "").strip()
            resource = f"/chats/{segment(chat_id)}/messages"

            if next_link:
                # The link carries the original order and time filter.
                url, params = check_next_link(graph, next_link, resource), None
            else:
                conditions = []
                if start:
                    if time_field != "lastModifiedDateTime":
                        # Graph only filters chat messages by a lower bound on lastModifiedDateTime.
                        raise GraphError("start_datetime needs time_field = lastModifiedDateTime.")
                    conditions.append(f"{time_field} gt {_utc(start, 'start_datetime')}")
                if end:
                    conditions.append(f"{time_field} lt {_utc(end, 'end_datetime')}")
                # Newest first is the only order Graph supports here.
                params = {"$top": top, "$orderby": f"{time_field} desc"}
                if conditions:
                    params["$filter"] = " and ".join(conditions)
                url = f"{graph.api_base}{resource}"

            page = paginate(graph, url, params, resource_path=resource, max_pages=max_pages)
        except GraphError as e:
            yield self.create_text_message(str(e))
            yield self.create_json_message({"error": str(e)})
            return

        raw = page.items if include_system else [m for m in page.items if m.get("messageType") == "message"]
        messages = [self._message(m, chat_id) for m in raw]
        pagination = {
            "complete": page.complete,
            "has_more": page.next_link is not None,
            "next_link": page.next_link,
            "pages_read": page.pages,
        }

        if messages:
            lines = [
                f"- [{m['created_date_time']}] {(m['from'] or {}).get('name') or 'system'}: {(m['body'] or '')[:120]}"
                for m in messages
            ]
            text = f"Found {len(messages)} message(s), newest first:\n" + "\n".join(lines)
        else:
            text = "No messages found."
        if page.next_link:
            text += "\nMore messages are available: pass next_link (with the same chat_id and include_system_events) to continue."
        if page.error:
            text += f"\nWarning: reading stopped early: {page.error}"
        yield self.create_text_message(text)
        result: dict[str, Any] = {"chat_id": chat_id, "messages": messages, "pagination": pagination}
        if page.error:
            result["warning"] = page.error
        yield self.create_json_message(result)

    @staticmethod
    def _message(m: dict, chat_id: str) -> dict:
        sender = m.get("from") or {}
        who = sender.get("user") or sender.get("application") or sender.get("device")
        body = m.get("body") or {}
        return {
            "id": m.get("id"),
            "chat_id": m.get("chatId") or chat_id,
            "message_type": m.get("messageType"),
            "from": {"id": who.get("id"), "name": who.get("displayName"), "kind": next(k for k in ("user", "application", "device") if sender.get(k))} if who else None,
            "body": body.get("content"),
            "content_type": body.get("contentType"),
            "created_date_time": m.get("createdDateTime"),
            "last_modified_date_time": m.get("lastModifiedDateTime"),
            "deleted_date_time": m.get("deletedDateTime"),
            "web_url": m.get("webUrl"),
            "event_detail": m.get("eventDetail"),
            "attachments": [
                {"id": a.get("id"), "name": a.get("name"), "content_type": a.get("contentType"), "content_url": a.get("contentUrl")}
                for a in m.get("attachments") or []
            ],
        }
