from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .. import base
from ..utils.filters import check_author_id, check_text_contains
from dify_plugin.interfaces.trigger import Event


class CommentCreatedEvent(base.NotionBaseEvent, Event):
    expected_type = "comment.created"

    def _check_entity_filters(
        self,
        entity_content: Mapping[str, Any] | None,
        parameters: Mapping[str, Any],
    ) -> None:
        check_author_id(entity_content, parameters.get("author_id"))
        check_text_contains(entity_content, parameters.get("text_contains"))
