from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class FormResponseReceivedEvent(Event):
    """Forward Typeform form_response payloads."""

    @staticmethod
    def _parse_filters(filter_value: str | None) -> dict[str, str]:
        if not filter_value:
            return {}
        filters: dict[str, str] = {}
        for part in filter_value.split(","):
            segment = part.strip()
            if not segment:
                continue
            if "=" not in segment:
                raise ValueError("Filter values must use key=value format")
            key, value = segment.split("=", 1)
            filters[key.strip()] = value.strip()
        return filters

    def _validate_hidden_filters(self, form_response: Mapping[str, Any], filters: dict[str, str]) -> None:
        if not filters:
            return

        hidden = form_response.get("hidden")
        if not isinstance(hidden, Mapping):
            raise EventIgnoreError()

        for key, expected in filters.items():
            value = hidden.get(key)
            if value is None or str(value) != expected:
                raise EventIgnoreError()

    def _validate_variable_filters(self, form_response: Mapping[str, Any], filters: dict[str, str]) -> None:
        if not filters:
            return

        variables = form_response.get("variables")
        if not isinstance(variables, list):
            raise EventIgnoreError()

        value_map: dict[str, str] = {}
        for item in variables:
            if not isinstance(item, Mapping):
                continue
            key = item.get("key")
            if not isinstance(key, str):
                continue
            if "number" in item and item.get("number") is not None:
                value = str(item["number"])
            elif "text" in item and item.get("text") is not None:
                value = str(item["text"])
            else:
                continue
            value_map[key] = value

        for key, expected in filters.items():
            if value_map.get(key) != expected:
                raise EventIgnoreError()

    def _on_event(
        self,
        request,
        parameters: Mapping[str, Any],
        payload: Mapping[str, Any] | None = None,
    ) -> Variables:
        payload = payload or request.get_json()
        if not isinstance(payload, Mapping):
            raise ValueError("No payload received")

        form_response = payload.get("form_response")
        if not isinstance(form_response, Mapping):
            raise ValueError("Missing form_response object")

        hidden_filters = self._parse_filters(parameters.get("hidden_field_filter"))
        variable_filters = self._parse_filters(parameters.get("variable_filter"))

        self._validate_hidden_filters(form_response=form_response, filters=hidden_filters)
        self._validate_variable_filters(form_response=form_response, filters=variable_filters)

        return Variables(variables={**payload})
