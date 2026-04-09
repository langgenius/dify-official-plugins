from __future__ import annotations

from collections.abc import Mapping, Sequence
from fnmatch import fnmatchcase
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class GoogleDriveChangeDetectedEvent(Event):
    """Fetch Google Drive change feed entries and expose them to workflows."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        credentials = self.runtime.credentials or {}
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Missing Google Drive OAuth access token in runtime credentials")

        spaces = self._resolve_spaces()
        change_types = self._normalize_string_list(parameters.get("change_types"))
        file_name_patterns = self._normalize_string_list(parameters.get("file_name_pattern"))

        changes = payload.get("changes", [])
        if not changes:
            raise EventIgnoreError("No Drive changes found in payload")

        filtered_changes = self._filter_changes(
            changes=changes,
            change_types=change_types,
            file_name_patterns=file_name_patterns,
        )

        if not filtered_changes:
            raise EventIgnoreError("No Drive changes matched the configured filters")

        variables = {
            "changes": filtered_changes,
            "spaces": spaces,
            "subscription": {
                "channel_id": self.runtime.subscription.properties.get("channel_id"),
                "resource_id": self.runtime.subscription.properties.get("resource_id"),
                "watch_expiration": self.runtime.subscription.properties.get("watch_expiration"),
                "user": self.runtime.subscription.properties.get("user"),
            },
        }

        return Variables(variables=variables)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_changes(
        self,
        *,
        changes: Sequence[Mapping[str, Any]],
        change_types: Sequence[str],
        file_name_patterns: Sequence[str],
    ) -> list[dict[str, Any]]:
        allowed_change_types = {change_type.lower() for change_type in change_types if change_type}
        normalized_patterns = [pattern for pattern in file_name_patterns if pattern]

        results: list[dict[str, Any]] = []
        for change in changes:
            removed = bool(change.get("removed"))

            file_info = change.get("file") or {}
            if not isinstance(file_info, Mapping):
                file_info = {}

            change_type_value = change.get("change_type") or change.get("changeType")
            normalized_change_type = str(change_type_value).lower() if change_type_value is not None else ""
            if allowed_change_types and normalized_change_type not in allowed_change_types:
                continue

            file_name = str(file_info.get("name") or "")
            if normalized_patterns and (
                not file_name or not any(fnmatchcase(file_name, pattern) for pattern in normalized_patterns)
            ):
                continue

            normalized = {
                "change_type": change.get("change_type") or change.get("changeType"),
                "removed": removed,
                "file_id": change.get("file_id") or change.get("fileId"),
                "file": dict(file_info),
            }
            results.append(normalized)
        return results

    def _resolve_spaces(self) -> list[str]:
        spaces = self.runtime.subscription.properties.get("spaces") or []
        if isinstance(spaces, str):
            return [part.strip() for part in spaces.split(",") if part.strip()]
        if isinstance(spaces, Sequence):
            return [str(space) for space in spaces if str(space)]
        return ["drive"]

    @staticmethod
    def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            integer = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, integer))

    @staticmethod
    def _to_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return default if value == "" else bool(value)

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.replace("\n", ",").split(",")]
            return [part for part in parts if part]
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
            results: list[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    results.append(text)
            return results
        text = str(value).strip()
        return [text] if text else []
