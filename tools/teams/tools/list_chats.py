from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import bounded_int, check_next_link, GraphError, paginate, resolve_graph_context
from tools.outputs import with_outputs

_CHAT_TYPES = ("oneOnOne", "group", "meeting")
# Graph expands at most this many members per chat; a chat at the cap may have more.
_MEMBER_EXPAND_CAP = 25


def _odata_string(value: str) -> str:
    """An OData string literal: wrap in single quotes and double any inside."""
    return "'" + value.replace("'", "''") + "'"


class ListChatsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            top = bounded_int(tool_parameters.get("top"), 20, 1, 50, "top")
            max_pages = bounded_int(tool_parameters.get("max_pages"), 5, 1, 10, "max_pages")
            name = (tool_parameters.get("participant_name") or "").strip()
            email = (tool_parameters.get("participant_email") or "").strip()
            chat_type = (tool_parameters.get("chat_type") or "all").strip()
            if chat_type != "all" and chat_type not in _CHAT_TYPES:
                raise GraphError("chat_type must be one of: all, oneOnOne, group, meeting.")
            next_link = (tool_parameters.get("next_link") or "").strip()

            if next_link:
                # The link carries the original filters; top, search and type inputs do not apply.
                url, params = check_next_link(graph, next_link, "/me/chats"), None
            else:
                conditions = []
                member = []
                if name:
                    member.append(f"o/displayName eq {_odata_string(name)}")
                if email:
                    member.append(f"o/microsoft.graph.aadUserConversationMember/email eq {_odata_string(email)}")
                if member:
                    # Name and email must match the same participant.
                    conditions.append(f"members/any(o: {' and '.join(member)})")
                if chat_type != "all":
                    conditions.append(f"chatType eq {_odata_string(chat_type)}")
                params = {"$expand": "members", "$top": top}
                if conditions:
                    params["$filter"] = " and ".join(conditions)
                url = f"{graph.api_base}/me/chats"

            page = paginate(graph, url, params, resource_path="/me/chats", max_pages=max_pages)
            me = graph.request("GET", "/me", params={"$select": "id"}).json().get("id")
        except GraphError as e:
            yield self.create_text_message(str(e))
            yield self.create_json_message({"error": str(e)})
            return

        chats = [self._chat(chat, me) for chat in page.items]
        pagination = {
            "complete": page.complete,
            "has_more": page.next_link is not None,
            "next_link": page.next_link,
            "pages_read": page.pages,
        }

        if chats:
            summary = "\n".join(f"- {c['display_name'] or c['chatType']} [{c['chatType']}] ({c['id']})" for c in chats)
            text = f"Found {len(chats)} chat(s):\n{summary}"
        else:
            text = "No chats found."
        if page.next_link:
            text += "\nMore chats are available: pass next_link to continue."
        if page.error:
            text += f"\nWarning: reading stopped early: {page.error}"
        yield self.create_text_message(text)
        result: dict[str, Any] = {"chats": chats, "pagination": pagination}
        if page.error:
            result["warning"] = page.error
        self._out.update(
            chats=[
                {"id": c["id"] or "", "display_name": c["display_name"] or "", "chat_type": c["chatType"] or "", "topic": c["topic"] or "",
                 "web_url": c["webUrl"] or "", "last_updated": c["lastUpdatedDateTime"] or "",
                 "member_names": [m["name"] or "" for m in c["members"]], "member_emails": [m["email"] or "" for m in c["members"]]}
                for c in chats
            ],
            count=len(chats), has_more=page.next_link is not None, next_link=page.next_link or "", success=True,
        )
        yield self.create_json_message(result)

    @staticmethod
    def _chat(chat: dict, me: str | None) -> dict:
        members = [
            {
                "name": m.get("displayName"),
                "user_id": m.get("userId"),
                "email": m.get("email"),
                "tenant_id": m.get("tenantId"),
                "is_me": bool(me) and m.get("userId") == me,
            }
            for m in chat.get("members") or []
        ]
        others = [m["name"] for m in members if not m["is_me"] and m["name"]]
        return {
            "id": chat.get("id"),
            "topic": chat.get("topic"),
            "chatType": chat.get("chatType"),
            # The topic if there is one, otherwise the other participants; never guessed.
            "display_name": chat.get("topic") or (", ".join(others) if others else None),
            "webUrl": chat.get("webUrl"),
            "createdDateTime": chat.get("createdDateTime"),
            "lastUpdatedDateTime": chat.get("lastUpdatedDateTime"),
            "members": members,
            "members_may_be_incomplete": len(members) >= _MEMBER_EXPAND_CAP,
        }
