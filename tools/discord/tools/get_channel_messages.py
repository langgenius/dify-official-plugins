import re
from typing import Any, Generator

import httpx
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


LIMIT_ERROR = "Invalid parameter: limit must be an integer between 1 and 100"


def _parse_limit(raw_limit: Any) -> tuple[int | None, str | None]:
    if raw_limit is None or raw_limit == "":
        return 50, None
    if isinstance(raw_limit, bool):
        return None, LIMIT_ERROR
    if isinstance(raw_limit, int):
        limit = raw_limit
    elif isinstance(raw_limit, str) and re.fullmatch(r"[+-]?\d+", raw_limit.strip()):
        limit = int(raw_limit)
    else:
        return None, LIMIT_ERROR
    if not 1 <= limit <= 100:
        return None, "Invalid parameter: limit must be between 1 and 100"
    return limit, None


class GetChannelMessagesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        bot_token = str(self.runtime.credentials.get("bot_token") or "").strip()
        if not bot_token:
            yield self.create_text_message("Missing bot_token credential")
            return

        channel_id = str(tool_parameters.get("channel_id") or "").strip()
        if not channel_id:
            yield self.create_text_message("Missing required parameter: channel_id")
            return

        limit, error = _parse_limit(tool_parameters.get("limit"))
        if error:
            yield self.create_text_message(error)
            return

        before = str(tool_parameters.get("before") or "").strip()
        after = str(tool_parameters.get("after") or "").strip()
        if before and after:
            yield self.create_text_message(
                "Invalid parameters: before and after cannot be used together"
            )
            return

        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        if after:
            params["after"] = after

        try:
            response = httpx.get(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {bot_token}"},
                params=params,
                timeout=30,
            )
        except httpx.RequestError:
            yield self.create_text_message("Unable to fetch messages from Discord")
            return

        if not response.is_success:
            yield self.create_text_message(
                f"Discord API error: status {response.status_code}, response: {response.text}"
            )
            return

        normalized = []
        for message in response.json():
            author = message.get("author") or {}
            normalized.append(
                {
                    "id": message.get("id"),
                    "channel_id": message.get("channel_id"),
                    "author_id": author.get("id"),
                    "author_username": author.get("username"),
                    "author_display_name": author.get("global_name"),
                    "author_bot": author.get("bot", False),
                    "content": message.get("content"),
                    "timestamp": message.get("timestamp"),
                    "edited_timestamp": message.get("edited_timestamp"),
                    "attachments": message.get("attachments", []),
                }
            )

        yield self.create_json_message(
            {
                "channel_id": channel_id,
                "count": len(normalized),
                "order": "newest_to_oldest",
                "next_before": normalized[-1]["id"] if normalized else None,
                "messages": normalized,
            }
        )
