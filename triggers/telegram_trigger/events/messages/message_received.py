from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class MessageReceivedEvent(TelegramUpdateEvent, Event):
    """Transform Telegram message updates into workflow variables."""

    update_key = "message"

    def _build_variables(
        self,
        payload: Mapping[str, Any],
        update: Mapping[str, Any] | list[Any] | str | int | None,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        message = dict(update or {})
        chat = message.get("chat", {})
        chat_type_filter = parameters.get("chat_type")
        if chat_type_filter and chat.get("type") != chat_type_filter:
            raise EventIgnoreError()

        keywords = parameters.get("text_contains")
        if keywords:
            content = (message.get("text") or message.get("caption") or "").lower()
            terms = [term.strip().lower() for term in keywords.split(",") if term.strip()]
            if terms and not any(term in content for term in terms):
                raise EventIgnoreError()

        return {
            "update_id": payload.get("update_id"),
            "message": message,
        }
