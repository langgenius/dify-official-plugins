from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError


class TelegramUpdateEvent:
    """Base class for Telegram webhook update events."""

    update_key: str = ""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = self._parse_payload(request)
        update = self._extract_update(payload)
        variables = self._build_variables(payload, update, parameters)
        return Variables(variables=variables)

    def _parse_payload(self, request: Request) -> Mapping[str, Any]:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received from Telegram")
        return payload

    def _extract_update(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | list[Any] | str | int | None:
        if not self.update_key:
            raise ValueError("update_key must be defined on TelegramUpdateEvent")
        update = payload.get(self.update_key)
        if update is None:
            raise EventIgnoreError()
        return update

    def _build_variables(
        self,
        payload: Mapping[str, Any],
        update: Mapping[str, Any] | list[Any] | str | int | None,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {"update_id": payload.get("update_id"), self.update_key: update}
