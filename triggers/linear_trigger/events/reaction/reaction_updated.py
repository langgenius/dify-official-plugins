from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ReactionUpdatedEvent(Event):
    """Linear reaction updated webhook event."""

    @staticmethod
    def _parse_list(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _get_target_type(data: Mapping[str, Any]) -> str:
        if data.get("issueId"):
            return "issue"
        if data.get("commentId"):
            return "comment"
        if data.get("projectUpdateId"):
            return "project_update"
        if data.get("initiativeUpdateId"):
            return "initiative_update"
        if data.get("postId"):
            return "post"
        return "unknown"

    def _check_emoji_filter(self, data: Mapping[str, Any], emoji_filter: str | None) -> None:
        allowed_emojis = self._parse_list(emoji_filter)
        if not allowed_emojis:
            return

        emoji = (data.get("emoji") or "").strip()
        if not emoji or emoji not in allowed_emojis:
            raise EventIgnoreError()

    def _check_target_type_filter(self, data: Mapping[str, Any], target_type_filter: str | None) -> None:
        allowed_targets = [item.lower() for item in self._parse_list(target_type_filter)]
        if not allowed_targets:
            return

        target_type = self._get_target_type(data)
        if target_type not in allowed_targets:
            raise EventIgnoreError()

    def _check_user_filter(self, data: Mapping[str, Any], user_filter: str | None) -> None:
        allowed_users = self._parse_list(user_filter)
        if not allowed_users:
            return

        user_id = (data.get("userId") or "").strip()
        if not user_id or user_id not in allowed_users:
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_emoji_filter(data, parameters.get("emoji_filter"))
        self._check_target_type_filter(data, parameters.get("target_type_filter"))
        self._check_user_filter(data, parameters.get("user_filter"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        reaction_data = payload.get("data")
        if not reaction_data:
            raise ValueError("No reaction data in payload")

        self._apply_filters(reaction_data, parameters)
        return Variables(variables={**payload})
