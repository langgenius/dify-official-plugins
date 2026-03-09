from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .. import base
from ..utils.filters import check_parent_id, check_parent_type
from dify_plugin.interfaces.trigger import Event


class DatabaseMovedEvent(base.NotionBaseEvent, Event):
    expected_type = "database.moved"

    def _check_entity_filters(
        self,
        entity_content: Mapping[str, Any] | None,
        parameters: Mapping[str, Any],
    ) -> None:
        check_parent_type(entity_content, parameters.get("parent_type"))
        check_parent_id(entity_content, parameters.get("parent_id"))
