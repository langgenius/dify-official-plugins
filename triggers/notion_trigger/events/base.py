from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError

from notion_client import NotionAPIError, NotionClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class NotionBaseEvent():
    """Base class for Notion webhook events."""

    expected_type: str = ""

    def _parse_workspace_filter(self, workspace_filter: str | None) -> set[str]:
        if not workspace_filter:
            return set()
        return {value.strip() for value in workspace_filter.split(",") if value.strip()}

    def _check_workspace_filter(self, payload: Mapping[str, Any], workspace_filter: str | None) -> None:
        allowed = self._parse_workspace_filter(workspace_filter)
        if not allowed:
            return
        workspace_id = payload.get("workspace_id")
        if workspace_id not in allowed:
            raise EventIgnoreError()

    def _validate_type(self, payload: Mapping[str, Any]) -> None:
        if self.expected_type and payload.get("type") != self.expected_type:
            raise EventIgnoreError()

    def _on_event(
        self,
        request: Request,
        parameters: Mapping[str, Any],
        payload: Mapping[str, Any] | None = None,
    ) -> Variables:
        payload = payload or request.get_json()
        if not isinstance(payload, Mapping) or not payload:
            raise ValueError("No payload received")

        self._validate_type(payload)
        self._check_workspace_filter(payload, parameters.get("workspace_filter"))

        integration_token = self._resolve_integration_token(parameters)
        entity_content = self._fetch_entity_content(payload, integration_token)
        block_children = self._maybe_fetch_block_children(payload, integration_token)

        result: dict[str, Any] = {**payload}
        if entity_content is not None:
            result["entity_content"] = entity_content
        if block_children is not None:
            result["block_children"] = block_children

        return Variables(variables=result)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _resolve_integration_token(self, parameters: Mapping[str, Any]) -> str | None:
        token = parameters.get("notion_integration_token")
        if token:
            return token

        runtime = getattr(self, "runtime", None)
        subscription = getattr(runtime, "subscription", None) if runtime else None
        if subscription:
            properties = getattr(subscription, "properties", None)
            if properties is None:
                properties = {}
            return properties.get("notion_integration_token")

        return None

    def _maybe_fetch_block_children(
        self,
        payload: Mapping[str, Any],
        integration_token: str | None,
    ) -> Mapping[str, Any] | None:
        if not integration_token:
            return None

        entity = payload.get("entity")
        if not isinstance(entity, Mapping) or entity.get("type") != "page":
            return None

        if self.expected_type not in {"page.content_updated", "page.created"}:
            return None

        page_id = entity.get("id")
        if not page_id:
            return None

        try:
            client = NotionClient(integration_token)
        except ValueError:
            return None

        try:
            return client.fetch_block_children(page_id)
        except NotionAPIError as exc:
            logger.warning("Failed to fetch block children for page %s: %s", page_id, exc)
            return None

    def _fetch_entity_content(self, payload: Mapping[str, Any], integration_token: str | None) -> Mapping[str, Any] | None:
        if not integration_token:
            return None

        entity = payload.get("entity")
        if not isinstance(entity, Mapping):
            return None

        entity_id = entity.get("id")
        entity_type = entity.get("type")
        if not entity_id:
            return None

        try:
            client = NotionClient(integration_token)
        except ValueError:
            return None

        data = payload.get("data")
        data_map: Mapping[str, Any] = data if isinstance(data, Mapping) else {}

        try:
            if entity_type == "page":
                return client.fetch_page(entity_id)
            if entity_type == "database":
                return client.fetch_database(entity_id)
            if entity_type == "data_source":
                return client.fetch_data_source(entity_id)
            if entity_type == "block":
                block = client.fetch_block(entity_id)
                return block
            if entity_type == "comment":
                parent = data_map.get("parent")
                block_id = None
                if isinstance(parent, Mapping):
                    block_id = parent.get("id")
                if not block_id:
                    block_id = data_map.get("page_id")
                discussion_id = data_map.get("discussion_id")
                return client.fetch_comment(
                    entity_id,
                    block_id=block_id,
                    discussion_id=discussion_id,
                )
        except NotionAPIError as exc:
            logger.warning(
                "Failed to hydrate Notion entity %s (%s): %s",
                entity_id,
                entity_type,
                exc,
            )

        return None
